package main

import (
	"context"
	"fmt"
	"os"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

// nuevoDB abre un pool de conexiones a Postgres, con la misma convención de
// variables de entorno y validación que modules/ingesta/storage.py's
// S3DbStorage: DB_HOST/DB_PORT/DB_NAME/DB_USER son obligatorias, DB_PASSWORD
// se lee directo del entorno (nunca se guarda en Config, para no filtrarla en
// logs de configuración), DB_SSLMODE y DB_CONNECT_TIMEOUT son opcionales.
func nuevoDB(ctx context.Context, cfg Config) (*pgxpool.Pool, error) {
	if err := faltantes("DB_HOST", cfg.DBHost, "DB_NAME", cfg.DBName, "DB_USER", cfg.DBUser); err != nil {
		return nil, err
	}
	password := os.Getenv("DB_PASSWORD")
	if password == "" {
		return nil, fmt.Errorf("falta la variable de entorno DB_PASSWORD")
	}

	dsn := fmt.Sprintf("host=%s port=%s dbname=%s user=%s password=%s connect_timeout=%d",
		cfg.DBHost, cfg.DBPort, cfg.DBName, cfg.DBUser, password, cfg.DBConnectTimeout)
	if cfg.DBSSLMode != "" {
		dsn += " sslmode=" + cfg.DBSSLMode
	}

	poolCfg, err := pgxpool.ParseConfig(dsn)
	if err != nil {
		return nil, fmt.Errorf("configuración de Postgres inválida: %w", err)
	}

	connectCtx, cancel := context.WithTimeout(ctx, time.Duration(cfg.DBConnectTimeout)*time.Second)
	defer cancel()
	pool, err := pgxpool.NewWithConfig(connectCtx, poolCfg)
	if err != nil {
		return nil, fmt.Errorf("no se pudo crear el pool de Postgres: %w", err)
	}
	if err := pool.Ping(connectCtx); err != nil {
		pool.Close()
		return nil, fmt.Errorf("no se pudo conectar a Postgres en %s:%s/%s: %w", cfg.DBHost, cfg.DBPort, cfg.DBName, err)
	}
	return pool, nil
}
