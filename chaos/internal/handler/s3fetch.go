package handler

import (
	"context"
	"fmt"
	"io"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/s3"
)

// S3Fetcher abstracts S3 operations needed by the handler.
type S3Fetcher interface {
	ListObjects(ctx context.Context, bucket, prefix string) ([]string, error)
	GetObject(ctx context.Context, bucket, key string) ([]byte, error)
}

// S3Client implements S3Fetcher using the real AWS S3 SDK.
type S3Client struct {
	api *s3.Client
}

// NewS3Client creates an S3Client from an S3 SDK client.
func NewS3Client(api *s3.Client) *S3Client {
	return &S3Client{api: api}
}

// ListObjects returns all object keys under the given prefix.
func (c *S3Client) ListObjects(ctx context.Context, bucket, prefix string) ([]string, error) {
	var keys []string
	var continuationToken *string

	for {
		out, err := c.api.ListObjectsV2(ctx, &s3.ListObjectsV2Input{
			Bucket:            aws.String(bucket),
			Prefix:            aws.String(prefix),
			ContinuationToken: continuationToken,
		})
		if err != nil {
			return nil, fmt.Errorf("list objects s3://%s/%s: %w", bucket, prefix, err)
		}

		for _, obj := range out.Contents {
			if obj.Key != nil {
				keys = append(keys, *obj.Key)
			}
		}

		if !aws.ToBool(out.IsTruncated) {
			break
		}
		continuationToken = out.NextContinuationToken
	}

	return keys, nil
}

// GetObject downloads the object body as bytes.
func (c *S3Client) GetObject(ctx context.Context, bucket, key string) ([]byte, error) {
	out, err := c.api.GetObject(ctx, &s3.GetObjectInput{
		Bucket: aws.String(bucket),
		Key:    aws.String(key),
	})
	if err != nil {
		return nil, fmt.Errorf("get object s3://%s/%s: %w", bucket, key, err)
	}
	defer out.Body.Close()

	data, err := io.ReadAll(out.Body)
	if err != nil {
		return nil, fmt.Errorf("read object s3://%s/%s: %w", bucket, key, err)
	}
	return data, nil
}
