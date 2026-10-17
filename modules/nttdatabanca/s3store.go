package main

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"io"
	"strings"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/aws/smithy-go"
)

// S3Store sube/baja el texto crudo de cada documento, igual que
// modules/ingesta/storage.py's S3DbStorage (_s3_key/_put_raw_text/_get_raw_text)
// y modules/nttbanca-n/app/services/s3.py's S3Service: la clave S3 queda en
// documents.source_uri, el texto nunca se guarda inline en Postgres.
type S3Store struct {
	client *s3.Client
	bucket string
	prefix string
}

// nuevoS3 valida S3_BUCKET_NAME (como faltantes() hace para el resto de
// clientes) y usa la cadena de credenciales por defecto de AWS (variables de
// entorno, ~/.aws/credentials, rol IAM) si AWS_ACCESS_KEY_ID/SECRET no están
// seteadas -- igual que boto3 en ambos módulos Python.
func nuevoS3(ctx context.Context, cfg Config) (*S3Store, error) {
	if err := faltantes("S3_BUCKET_NAME", cfg.S3BucketName); err != nil {
		return nil, err
	}
	var opts []func(*config.LoadOptions) error
	if cfg.AWSRegion != "" {
		opts = append(opts, config.WithRegion(cfg.AWSRegion))
	}
	awsCfg, err := config.LoadDefaultConfig(ctx, opts...)
	if err != nil {
		return nil, fmt.Errorf("no se pudo cargar la configuración de AWS: %w", err)
	}
	client := s3.NewFromConfig(awsCfg, func(o *s3.Options) {
		if cfg.S3EndpointURL != "" {
			o.BaseEndpoint = aws.String(cfg.S3EndpointURL)
			o.UsePathStyle = true // compatible con MinIO/LocalStack para desarrollo local
		}
	})
	return &S3Store{client: client, bucket: cfg.S3BucketName, prefix: strings.Trim(cfg.S3KeyPrefix, "/")}, nil
}

func (s *S3Store) key(docID string) string {
	if s.prefix == "" {
		return docID + ".txt"
	}
	return s.prefix + "/" + docID + ".txt"
}

// PutRawText sube el texto completo del documento y devuelve la key (lo que
// se guarda en documents.source_uri).
func (s *S3Store) PutRawText(ctx context.Context, docID, text string) (string, error) {
	key := s.key(docID)
	_, err := s.client.PutObject(ctx, &s3.PutObjectInput{
		Bucket:      aws.String(s.bucket),
		Key:         aws.String(key),
		Body:        bytes.NewReader([]byte(text)),
		ContentType: aws.String("text/plain; charset=utf-8"),
	})
	if err != nil {
		return "", fmt.Errorf("s3 put %q: %w", key, err)
	}
	return key, nil
}

// GetRawText devuelve (texto, true) o ("", false) si la key no existe.
func (s *S3Store) GetRawText(ctx context.Context, key string) (string, bool, error) {
	out, err := s.client.GetObject(ctx, &s3.GetObjectInput{Bucket: aws.String(s.bucket), Key: aws.String(key)})
	if err != nil {
		var apiErr smithy.APIError
		if errors.As(err, &apiErr) && (apiErr.ErrorCode() == "NoSuchKey" || apiErr.ErrorCode() == "NotFound") {
			return "", false, nil
		}
		return "", false, fmt.Errorf("s3 get %q: %w", key, err)
	}
	defer out.Body.Close()
	data, err := io.ReadAll(out.Body)
	if err != nil {
		return "", false, fmt.Errorf("s3 get %q: leyendo body: %w", key, err)
	}
	return string(data), true, nil
}
