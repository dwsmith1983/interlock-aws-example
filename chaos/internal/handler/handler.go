package handler

import (
	"context"
	"fmt"
	"math/rand"
	"regexp"
	"strings"
	"time"

	"gopkg.in/yaml.v3"

	"github.com/dwsmith1983/chaos-data/pkg/adapter"
	"github.com/dwsmith1983/chaos-data/pkg/engine"
	"github.com/dwsmith1983/chaos-data/pkg/mutation"
	"github.com/dwsmith1983/chaos-data/pkg/scenario"
	"github.com/dwsmith1983/chaos-data/pkg/types"
)

// validScenarioName restricts scenario names to safe characters only,
// preventing path-traversal attacks when the name is used to build S3 keys.
var validScenarioName = regexp.MustCompile(`^[a-zA-Z0-9_-]+$`)

const (
	modeDeterministic = "deterministic"
	modeProbabilistic = "probabilistic"
)

// ChaosInput is the Lambda event payload.
type ChaosInput struct {
	Scenario string `json:"scenario,omitempty"` // empty = probabilistic
	Severity string `json:"severity,omitempty"` // override max severity
}

// ChaosOutput is the Lambda response.
type ChaosOutput struct {
	ExperimentID       string `json:"experiment_id"`
	Mode               string `json:"mode"`
	ScenariosEvaluated int    `json:"scenarios_evaluated"`
	MutationsApplied   int    `json:"mutations_applied"`
	MutationsSkipped   int    `json:"mutations_skipped"`
	Error              string `json:"error,omitempty"`
}

// Handler is the core chaos controller.
type Handler struct {
	s3Fetcher   S3Fetcher
	transport   adapter.DataTransport
	emitter     adapter.EventEmitter
	sensorStore adapter.SensorStore
	safetyCtrl  adapter.SafetyController
	resolver    adapter.DependencyResolver
	bucket      string
	prefix      string
	maxSeverity types.Severity
}

// Config holds Handler construction parameters.
type Config struct {
	S3Fetcher   S3Fetcher
	Transport   adapter.DataTransport
	Emitter     adapter.EventEmitter
	SensorStore adapter.SensorStore
	SafetyCtrl  adapter.SafetyController
	Resolver    adapter.DependencyResolver
	Bucket      string
	Prefix      string
	MaxSeverity types.Severity
}

// New creates a Handler from the given Config.
func New(cfg Config) *Handler {
	return &Handler{
		s3Fetcher:   cfg.S3Fetcher,
		transport:   cfg.Transport,
		emitter:     cfg.Emitter,
		sensorStore: cfg.SensorStore,
		safetyCtrl:  cfg.SafetyCtrl,
		resolver:    cfg.Resolver,
		bucket:      cfg.Bucket,
		prefix:      cfg.Prefix,
		maxSeverity: cfg.MaxSeverity,
	}
}

// Handle processes a chaos event: loads scenarios from S3, configures the
// chaos-data engine, and runs in deterministic or probabilistic mode.
func (h *Handler) Handle(ctx context.Context, input ChaosInput) (ChaosOutput, error) {
	// Generate a unique experiment ID for this invocation so that every
	// ChaosEvent emitted during this run shares a distinct DynamoDB
	// partition key.
	experimentID := fmt.Sprintf("chaos-%d", time.Now().UnixNano())

	// Determine effective max severity.
	maxSev := h.maxSeverity
	if input.Severity != "" {
		parsed, err := types.ParseSeverity(input.Severity)
		if err != nil {
			return ChaosOutput{ExperimentID: experimentID, Error: fmt.Sprintf("invalid severity: %v", err)}, err
		}
		maxSev = parsed
	}

	// Validate scenario name to prevent path traversal in S3 key construction.
	if input.Scenario != "" {
		if !validScenarioName.MatchString(input.Scenario) {
			return ChaosOutput{ExperimentID: experimentID, Error: "invalid scenario name"}, fmt.Errorf("invalid scenario name %q: must match [a-zA-Z0-9_-]+", input.Scenario)
		}
	}

	// Load scenarios from S3.
	scenarios, err := h.loadScenarios(ctx, input.Scenario)
	if err != nil {
		return ChaosOutput{ExperimentID: experimentID, Error: fmt.Sprintf("load scenarios: %v", err)}, err
	}

	if len(scenarios) == 0 {
		return ChaosOutput{
			ExperimentID:       experimentID,
			Mode:               h.mode(input),
			ScenariosEvaluated: 0,
		}, nil
	}

	// Filter scenarios that exceed the effective max severity. The engine
	// delegates severity filtering to SafetyController, but when no
	// controller is configured we must filter here.
	filtered := filterBySeverity(scenarios, maxSev)

	// Build mutation registry with the mutations used by loaded scenarios.
	registry := mutation.NewRegistry()
	if err := h.registerMutations(registry, filtered); err != nil {
		return ChaosOutput{ExperimentID: experimentID, Error: fmt.Sprintf("register mutations: %v", err)}, err
	}

	// Determine mode.
	mode := h.mode(input)

	// Build engine config.
	engineCfg := types.EngineConfig{
		Mode: mode,
	}

	// Build engine options. Wrap the emitter so that every ChaosEvent
	// carries this invocation's ExperimentID.
	var opts []engine.EngineOption
	if h.emitter != nil {
		opts = append(opts, engine.WithEmitter(&experimentEmitter{
			experimentID: experimentID,
			delegate:     h.emitter,
		}))
	}
	if h.safetyCtrl != nil {
		opts = append(opts, engine.WithSafety(h.safetyCtrl))
	}
	if h.resolver != nil {
		opts = append(opts, engine.WithDependencyResolver(h.resolver))
	}

	eng := engine.New(engineCfg, h.transport, registry, filtered, opts...)

	// Run the engine.
	var records []types.MutationRecord
	if mode == modeDeterministic {
		records, err = eng.Run(ctx)
	} else {
		// Probabilistic: run a single iteration with 1s timeout.
		probCtx, cancel := context.WithTimeout(ctx, 1*time.Second)
		defer cancel()
		//nolint:gosec // Cryptographic randomness not needed for chaos selection.
		rng := rand.New(rand.NewSource(time.Now().UnixNano()))
		records, err = eng.RunProbabilistic(probCtx, 500*time.Millisecond, rng)
	}

	if err != nil {
		return ChaosOutput{
			ExperimentID: experimentID,
			Mode:         mode,
			Error:        fmt.Sprintf("engine run: %v", err),
		}, err
	}

	// Count applied vs skipped.
	applied := 0
	skipped := 0
	for _, r := range records {
		if r.Applied {
			applied++
		} else {
			skipped++
		}
	}

	return ChaosOutput{
		ExperimentID:       experimentID,
		Mode:               mode,
		ScenariosEvaluated: len(filtered),
		MutationsApplied:   applied,
		MutationsSkipped:   skipped,
	}, nil
}

// mode returns "deterministic" if a specific scenario is requested,
// "probabilistic" otherwise.
func (h *Handler) mode(input ChaosInput) string {
	if input.Scenario != "" {
		return modeDeterministic
	}
	return modeProbabilistic
}

// filterBySeverity returns only scenarios whose severity does not exceed
// the given threshold.
func filterBySeverity(scenarios []scenario.Scenario, maxSev types.Severity) []scenario.Scenario {
	result := make([]scenario.Scenario, 0, len(scenarios))
	for _, sc := range scenarios {
		if !sc.Severity.ExceedsThreshold(maxSev) {
			result = append(result, sc)
		}
	}
	return result
}

// loadScenarios fetches YAML scenarios from S3.
// If scenarioName is non-empty, loads only that one file.
// If empty, loads all YAML files under the prefix.
func (h *Handler) loadScenarios(ctx context.Context, scenarioName string) ([]scenario.Scenario, error) {
	if scenarioName != "" {
		key := h.prefix + scenarioName + ".yaml"
		data, err := h.s3Fetcher.GetObject(ctx, h.bucket, key)
		if err != nil {
			return nil, fmt.Errorf("fetch scenario %q: %w", key, err)
		}

		var sc scenario.Scenario
		if err := yaml.Unmarshal(data, &sc); err != nil {
			return nil, fmt.Errorf("parse scenario %q: %w", key, err)
		}
		if err := sc.Validate(); err != nil {
			return nil, fmt.Errorf("validate scenario %q: %w", key, err)
		}

		return []scenario.Scenario{sc}, nil
	}

	// Probabilistic: load all scenarios.
	keys, err := h.s3Fetcher.ListObjects(ctx, h.bucket, h.prefix)
	if err != nil {
		return nil, fmt.Errorf("list scenarios: %w", err)
	}

	var scenarios []scenario.Scenario
	for _, key := range keys {
		lower := strings.ToLower(key)
		if !strings.HasSuffix(lower, ".yaml") && !strings.HasSuffix(lower, ".yml") {
			continue
		}

		data, err := h.s3Fetcher.GetObject(ctx, h.bucket, key)
		if err != nil {
			return nil, fmt.Errorf("fetch scenario %q: %w", key, err)
		}

		var sc scenario.Scenario
		if err := yaml.Unmarshal(data, &sc); err != nil {
			return nil, fmt.Errorf("parse scenario %q: %w", key, err)
		}
		if err := sc.Validate(); err != nil {
			return nil, fmt.Errorf("validate scenario %q: %w", key, err)
		}

		scenarios = append(scenarios, sc)
	}

	return scenarios, nil
}

// experimentEmitter wraps an EventEmitter and stamps every emitted event
// with a fixed ExperimentID. This ensures all events from a single handler
// invocation share the same partition key in DynamoDB.
type experimentEmitter struct {
	experimentID string
	delegate     adapter.EventEmitter
}

func (e *experimentEmitter) Emit(ctx context.Context, event types.ChaosEvent) error {
	event.ExperimentID = e.experimentID
	return e.delegate.Emit(ctx, event)
}

// registerMutations adds mutation implementations to the registry based on
// what the loaded scenarios require.
func (h *Handler) registerMutations(registry *mutation.Registry, scenarios []scenario.Scenario) error {
	needed := make(map[string]struct{})
	for _, sc := range scenarios {
		needed[sc.Mutation.Type] = struct{}{}
	}

	for mutType := range needed {
		var m mutation.Mutation
		switch mutType {
		case "delay":
			m = &mutation.DelayMutation{}
		case "post-run-drift":
			m = &mutation.PostRunDriftMutation{}
		case "phantom-sensor":
			if h.sensorStore == nil {
				return fmt.Errorf("phantom-sensor mutation requires a SensorStore")
			}
			m = mutation.NewPhantomSensorMutation(h.sensorStore)
		default:
			return fmt.Errorf("unsupported mutation type %q", mutType)
		}

		if err := registry.Register(m); err != nil {
			return fmt.Errorf("register %q: %w", mutType, err)
		}
	}

	return nil
}
