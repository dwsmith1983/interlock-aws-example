package handler

import (
	"context"
	"errors"
	"io"
	"strings"
	"testing"
	"time"

	"github.com/dwsmith1983/chaos-data/pkg/adapter"
	"github.com/dwsmith1983/chaos-data/pkg/types"
)

// mockS3Fetcher implements the S3Fetcher interface for testing.
type mockS3Fetcher struct {
	objects map[string]string // key -> YAML content
	listErr error
	getErr  error
}

func (m *mockS3Fetcher) ListObjects(_ context.Context, _, prefix string) ([]string, error) {
	if m.listErr != nil {
		return nil, m.listErr
	}
	var keys []string
	for k := range m.objects {
		if strings.HasPrefix(k, prefix) {
			keys = append(keys, k)
		}
	}
	return keys, nil
}

func (m *mockS3Fetcher) GetObject(_ context.Context, _, key string) ([]byte, error) {
	if m.getErr != nil {
		return nil, m.getErr
	}
	data, ok := m.objects[key]
	if !ok {
		return nil, adapter.ErrNotFound
	}
	return []byte(data), nil
}

// mockTransport implements adapter.DataTransport for testing.
type mockTransport struct {
	objects []types.DataObject
}

func (m *mockTransport) List(_ context.Context, _ string) ([]types.DataObject, error) {
	return m.objects, nil
}

func (m *mockTransport) Read(_ context.Context, _ string) (io.ReadCloser, error) {
	return io.NopCloser(strings.NewReader("")), nil
}

func (m *mockTransport) Write(_ context.Context, _ string, _ io.Reader) error { return nil }
func (m *mockTransport) Delete(_ context.Context, _ string) error             { return nil }
func (m *mockTransport) Hold(_ context.Context, _ string, _ time.Time) error  { return nil }
func (m *mockTransport) Release(_ context.Context, _ string) error            { return nil }
func (m *mockTransport) ReleaseAll(_ context.Context) error                   { return nil }
func (m *mockTransport) HoldData(_ context.Context, _ string, _ io.Reader, _ time.Time) error {
	return nil
}
func (m *mockTransport) ListHeld(_ context.Context) ([]types.HeldObject, error) {
	return nil, nil
}

// mockEmitter implements adapter.EventEmitter for testing.
type mockEmitter struct {
	events []types.ChaosEvent
}

func (m *mockEmitter) Emit(_ context.Context, event types.ChaosEvent) error {
	m.events = append(m.events, event)
	return nil
}

const lateDataYAML = `name: late-data-bronze
description: Delays S3 objects to simulate late-arriving data
category: data-arrival
severity: moderate
version: 1
target:
  layer: data
  transport: s3
  filter:
    prefix: raw/cdr/
probability: 0.3
safety:
  max_affected_pct: 25
  cooldown: 5m
  sla_aware: true
mutation:
  type: delay
  params:
    duration: "30m"
    release: "true"
expected_response:
  within: 10m
  asserts:
    - type: interlock_event
      target: bronze-cdr
      condition: exists
`

func TestHandle_Deterministic_LoadsScenarioAndRuns(t *testing.T) {
	t.Parallel()

	fetcher := &mockS3Fetcher{
		objects: map[string]string{
			"chaos/scenarios/late-data-bronze.yaml": lateDataYAML,
		},
	}

	transport := &mockTransport{
		objects: []types.DataObject{
			{Key: "raw/cdr/2026-03-29/file001.parquet", Size: 1024},
		},
	}

	emitter := &mockEmitter{}

	h := &Handler{
		s3Fetcher:   fetcher,
		transport:   transport,
		emitter:     emitter,
		bucket:      "test-bucket",
		prefix:      "chaos/scenarios/",
		maxSeverity: types.SeverityModerate,
	}

	input := ChaosInput{
		Scenario: "late-data-bronze",
	}

	result, err := h.Handle(context.Background(), input)
	if err != nil {
		t.Fatalf("Handle() error = %v", err)
	}

	if result.ExperimentID == "" {
		t.Error("ExperimentID is empty, want non-empty")
	}

	if !strings.HasPrefix(result.ExperimentID, "chaos-") {
		t.Errorf("ExperimentID = %q, want prefix %q", result.ExperimentID, "chaos-")
	}

	if result.ScenariosEvaluated != 1 {
		t.Errorf("ScenariosEvaluated = %d, want 1", result.ScenariosEvaluated)
	}

	if result.Mode != "deterministic" {
		t.Errorf("Mode = %q, want %q", result.Mode, "deterministic")
	}
}

func TestHandle_Probabilistic_LoadsAllScenarios(t *testing.T) {
	t.Parallel()

	fetcher := &mockS3Fetcher{
		objects: map[string]string{
			"chaos/scenarios/late-data-bronze.yaml": lateDataYAML,
		},
	}

	transport := &mockTransport{
		objects: []types.DataObject{
			{Key: "raw/cdr/2026-03-29/file001.parquet", Size: 1024},
		},
	}

	emitter := &mockEmitter{}

	h := &Handler{
		s3Fetcher:   fetcher,
		transport:   transport,
		emitter:     emitter,
		bucket:      "test-bucket",
		prefix:      "chaos/scenarios/",
		maxSeverity: types.SeverityModerate,
	}

	// Empty Scenario field = probabilistic mode.
	input := ChaosInput{}

	result, err := h.Handle(context.Background(), input)
	if err != nil {
		t.Fatalf("Handle() error = %v", err)
	}

	if result.ExperimentID == "" {
		t.Error("ExperimentID is empty, want non-empty")
	}

	if !strings.HasPrefix(result.ExperimentID, "chaos-") {
		t.Errorf("ExperimentID = %q, want prefix %q", result.ExperimentID, "chaos-")
	}

	if result.Mode != "probabilistic" {
		t.Errorf("Mode = %q, want %q", result.Mode, "probabilistic")
	}
}

func TestHandle_SeverityOverride(t *testing.T) {
	t.Parallel()

	fetcher := &mockS3Fetcher{
		objects: map[string]string{
			"chaos/scenarios/late-data-bronze.yaml": lateDataYAML,
		},
	}

	transport := &mockTransport{
		objects: []types.DataObject{
			{Key: "raw/cdr/2026-03-29/file001.parquet", Size: 1024},
		},
	}

	emitter := &mockEmitter{}

	h := &Handler{
		s3Fetcher:   fetcher,
		transport:   transport,
		emitter:     emitter,
		bucket:      "test-bucket",
		prefix:      "chaos/scenarios/",
		maxSeverity: types.SeverityModerate,
	}

	// Severity override to "low" should skip the "moderate" scenario.
	input := ChaosInput{
		Severity: "low",
	}

	result, err := h.Handle(context.Background(), input)
	if err != nil {
		t.Fatalf("Handle() error = %v", err)
	}

	// Scenario is moderate severity, but max is set to low -- should be skipped.
	if result.MutationsApplied != 0 {
		t.Errorf("MutationsApplied = %d, want 0 (severity filter)", result.MutationsApplied)
	}
}

func TestHandle_S3FetchFailure(t *testing.T) {
	t.Parallel()

	fetchErr := errors.New("s3 access denied")
	fetcher := &mockS3Fetcher{
		objects: map[string]string{},
		listErr: fetchErr,
	}

	transport := &mockTransport{}
	emitter := &mockEmitter{}

	h := &Handler{
		s3Fetcher:   fetcher,
		transport:   transport,
		emitter:     emitter,
		bucket:      "test-bucket",
		prefix:      "chaos/scenarios/",
		maxSeverity: types.SeverityModerate,
	}

	input := ChaosInput{}

	_, err := h.Handle(context.Background(), input)
	if err == nil {
		t.Fatal("Handle() should return error on S3 fetch failure")
	}

	if !strings.Contains(err.Error(), "s3 access denied") {
		t.Errorf("error = %q, want to contain %q", err.Error(), "s3 access denied")
	}
}

func TestHandle_ScenarioNameValidation(t *testing.T) {
	t.Parallel()

	transport := &mockTransport{}
	emitter := &mockEmitter{}

	h := &Handler{
		s3Fetcher:   &mockS3Fetcher{objects: map[string]string{}},
		transport:   transport,
		emitter:     emitter,
		bucket:      "test-bucket",
		prefix:      "chaos/scenarios/",
		maxSeverity: types.SeverityModerate,
	}

	tests := []struct {
		name      string
		scenario  string
		wantErr   bool
		errSubstr string
	}{
		{name: "valid simple name", scenario: "late-data-bronze", wantErr: false},
		{name: "valid with underscore", scenario: "my_scenario", wantErr: false},
		{name: "valid with digits", scenario: "scenario123", wantErr: false},
		{name: "path traversal with dots", scenario: "../etc/passwd", wantErr: true, errSubstr: "invalid scenario name"},
		{name: "forward slash", scenario: "foo/bar", wantErr: true, errSubstr: "invalid scenario name"},
		{name: "backslash", scenario: `foo\bar`, wantErr: true, errSubstr: "invalid scenario name"},
		{name: "double dot only", scenario: "..", wantErr: true, errSubstr: "invalid scenario name"},
		{name: "space in name", scenario: "foo bar", wantErr: true, errSubstr: "invalid scenario name"},
		{name: "empty scenario (probabilistic)", scenario: "", wantErr: false},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			input := ChaosInput{Scenario: tc.scenario}
			_, err := h.Handle(context.Background(), input)

			if tc.wantErr {
				if err == nil {
					t.Fatalf("Handle() expected error for scenario %q, got nil", tc.scenario)
				}
				if !strings.Contains(err.Error(), tc.errSubstr) {
					t.Errorf("error = %q, want to contain %q", err.Error(), tc.errSubstr)
				}
			} else if err != nil && tc.scenario != "" {
				// For valid non-empty names the mock may return ErrNotFound
				// from GetObject, which is expected since we did not seed the
				// scenario. We only care that the validation itself did NOT
				// reject the name.
				if strings.Contains(err.Error(), "invalid scenario name") {
					t.Fatalf("Handle() rejected valid scenario name %q: %v", tc.scenario, err)
				}
			}
		})
	}
}

func TestHandle_ExperimentID_UniquePerInvocation(t *testing.T) {
	t.Parallel()

	fetcher := &mockS3Fetcher{
		objects: map[string]string{
			"chaos/scenarios/late-data-bronze.yaml": lateDataYAML,
		},
	}

	transport := &mockTransport{
		objects: []types.DataObject{
			{Key: "raw/cdr/2026-03-29/file001.parquet", Size: 1024},
		},
	}

	emitter := &mockEmitter{}

	h := &Handler{
		s3Fetcher:   fetcher,
		transport:   transport,
		emitter:     emitter,
		bucket:      "test-bucket",
		prefix:      "chaos/scenarios/",
		maxSeverity: types.SeverityModerate,
	}

	input := ChaosInput{Scenario: "late-data-bronze"}

	result1, err := h.Handle(context.Background(), input)
	if err != nil {
		t.Fatalf("Handle() first call error = %v", err)
	}

	result2, err := h.Handle(context.Background(), input)
	if err != nil {
		t.Fatalf("Handle() second call error = %v", err)
	}

	if result1.ExperimentID == result2.ExperimentID {
		t.Errorf("two invocations produced the same ExperimentID %q", result1.ExperimentID)
	}
}

func TestHandle_ExperimentID_StampedOnEmittedEvents(t *testing.T) {
	t.Parallel()

	fetcher := &mockS3Fetcher{
		objects: map[string]string{
			"chaos/scenarios/late-data-bronze.yaml": lateDataYAML,
		},
	}

	transport := &mockTransport{
		objects: []types.DataObject{
			{Key: "raw/cdr/2026-03-29/file001.parquet", Size: 1024},
		},
	}

	emitter := &mockEmitter{}

	h := &Handler{
		s3Fetcher:   fetcher,
		transport:   transport,
		emitter:     emitter,
		bucket:      "test-bucket",
		prefix:      "chaos/scenarios/",
		maxSeverity: types.SeverityModerate,
	}

	input := ChaosInput{Scenario: "late-data-bronze"}

	result, err := h.Handle(context.Background(), input)
	if err != nil {
		t.Fatalf("Handle() error = %v", err)
	}

	if len(emitter.events) == 0 {
		t.Fatal("expected at least one emitted event, got none")
	}

	for i, ev := range emitter.events {
		if ev.ExperimentID != result.ExperimentID {
			t.Errorf("emitter.events[%d].ExperimentID = %q, want %q",
				i, ev.ExperimentID, result.ExperimentID)
		}
	}
}

func TestHandle_Deterministic_GetObjectFailure(t *testing.T) {
	t.Parallel()

	fetchErr := errors.New("s3 get object failed")
	fetcher := &mockS3Fetcher{
		objects: map[string]string{},
		getErr:  fetchErr,
	}

	transport := &mockTransport{}
	emitter := &mockEmitter{}

	h := &Handler{
		s3Fetcher:   fetcher,
		transport:   transport,
		emitter:     emitter,
		bucket:      "test-bucket",
		prefix:      "chaos/scenarios/",
		maxSeverity: types.SeverityModerate,
	}

	input := ChaosInput{Scenario: "late-data-bronze"}

	_, err := h.Handle(context.Background(), input)
	if err == nil {
		t.Fatal("Handle() should return error when GetObject fails in deterministic mode")
	}

	if !strings.Contains(err.Error(), "s3 get object failed") {
		t.Errorf("error = %q, want to contain %q", err.Error(), "s3 get object failed")
	}
}
