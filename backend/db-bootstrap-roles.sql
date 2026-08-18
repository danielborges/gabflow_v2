\set ON_ERROR_STOP on

SELECT format(
    'CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS PASSWORD %L',
    :'app_role',
    :'app_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_role')
\gexec

SELECT format(
    'ALTER ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS PASSWORD %L',
    :'app_role',
    :'app_password'
)
\gexec

SELECT format(
    'CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS PASSWORD %L',
    :'worker_role',
    :'worker_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'worker_role')
\gexec

SELECT format(
    'ALTER ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS PASSWORD %L',
    :'worker_role',
    :'worker_password'
)
\gexec

SELECT format(
    'CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT BYPASSRLS PASSWORD %L',
    :'backup_role',
    :'backup_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'backup_role')
\gexec

SELECT format(
    'ALTER ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT BYPASSRLS PASSWORD %L',
    :'backup_role',
    :'backup_password'
)
\gexec

SELECT format('GRANT CONNECT ON DATABASE %I TO %I', :'database_name', :'app_role')
\gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', :'database_name', :'worker_role')
\gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', :'database_name', :'backup_role')
\gexec

SELECT format('GRANT USAGE ON SCHEMA public TO %I', :'app_role')
\gexec
SELECT format('GRANT USAGE ON SCHEMA public TO %I', :'worker_role')
\gexec

SELECT format('GRANT USAGE ON SCHEMA rag_global TO %I', :'app_role')
WHERE EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'rag_global')
\gexec
SELECT format('GRANT USAGE ON SCHEMA rag_global TO %I', :'worker_role')
WHERE EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'rag_global')
\gexec

SELECT format(
    'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO %I',
    :'app_role'
)
\gexec
SELECT format(
    'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO %I',
    :'worker_role'
)
\gexec
SELECT format('GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO %I', :'app_role')
\gexec
SELECT format('GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO %I', :'worker_role')
\gexec

SELECT format(
    'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA rag_global TO %I',
    :'app_role'
)
WHERE EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'rag_global')
\gexec
SELECT format(
    'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA rag_global TO %I',
    :'worker_role'
)
WHERE EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'rag_global')
\gexec
SELECT format(
    'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA rag_global TO %I',
    :'app_role'
)
WHERE EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'rag_global')
\gexec
SELECT format(
    'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA rag_global TO %I',
    :'worker_role'
)
WHERE EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'rag_global')
\gexec

SELECT format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public '
    'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO %I',
    :'migrator_role',
    :'app_role'
)
\gexec
SELECT format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public '
    'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO %I',
    :'migrator_role',
    :'worker_role'
)
\gexec
SELECT format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public '
    'GRANT USAGE, SELECT ON SEQUENCES TO %I',
    :'migrator_role',
    :'app_role'
)
\gexec
SELECT format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public '
    'GRANT USAGE, SELECT ON SEQUENCES TO %I',
    :'migrator_role',
    :'worker_role'
)
\gexec

SELECT format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA rag_global '
    'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO %I',
    :'migrator_role',
    :'app_role'
)
WHERE EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'rag_global')
\gexec
SELECT format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA rag_global '
    'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO %I',
    :'migrator_role',
    :'worker_role'
)
WHERE EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'rag_global')
\gexec
SELECT format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA rag_global '
    'GRANT USAGE, SELECT ON SEQUENCES TO %I',
    :'migrator_role',
    :'app_role'
)
WHERE EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'rag_global')
\gexec
SELECT format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA rag_global '
    'GRANT USAGE, SELECT ON SEQUENCES TO %I',
    :'migrator_role',
    :'worker_role'
)
WHERE EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'rag_global')
\gexec

GRANT pg_read_all_data TO :"backup_role";
