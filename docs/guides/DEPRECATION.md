# Deprecation Policy

## Overview

This document outlines the deprecation policy for SkinLens v1.0 and the plan for removing legacy v2 code.

## Deprecation Policy

### Version Strategy

- **Current Version**: v1.0
- **Next Major Version**: v2.0 (planned for Q3 2026)
- **Deprecation Period**: 6 months minimum for any deprecated feature

### Deprecation Process

1. **Mark as Deprecated**: Add `DeprecationWarning` to deprecated functions/aliases
2. **Documentation**: Update documentation to indicate deprecation
3. **Migration Guide**: Provide clear migration instructions
4. **Removal**: Remove deprecated code in the next major version

## Current Deprecations

### v2 Legacy Aliases (Deprecated in v1.0, Remove in v2.0)

The following v2 legacy aliases are deprecated and will be removed in v2.0:

| Deprecated Alias | Replacement | Location | Warning |
|-----------------|-------------|----------|---------|
| `_compute_overall_score_v2` | `_compute_overall_score_legacy` | `src/scoring/_core.py` | ✅ |
| `_V2_MEASUREMENT_CATEGORIES` | `_LEGACY_MEASUREMENT_CATEGORIES` | `src/scoring/_core.py` | ⚠️ 상수 (warning 불가) |
| `_measurement_report_string_v2` | `_measurement_report_string_legacy` | `src/scoring/_core.py` | ✅ |
| `_MEASUREMENT_CATEGORIES` | `_LEGACY_MEASUREMENT_CATEGORIES` | `src/scoring/skin_scoring.py` | ⚠️ 상수 (warning 불가) |
| `SkinAnalyzerV3` | `SkinAnalyzer` | `src/scoring/skin_scoring.py` | ⚠️ 상수 (warning 불가) |
| `SkinAnalyzer._core_to_v3` | `SkinAnalyzer._legacy_to_current` | `src/scoring/skin_scoring.py` | ⚠️ 메서드 (warning 불가) |

**Migration Guide**:
- Replace `_compute_overall_score_v2` with `_compute_overall_score_legacy`
- Replace `_V2_MEASUREMENT_CATEGORIES` with `_LEGACY_MEASUREMENT_CATEGORIES`
- Replace `_measurement_report_string_v2` with `_measurement_report_string_legacy`
- Replace `_MEASUREMENT_CATEGORIES` with `_LEGACY_MEASUREMENT_CATEGORIES`
- Replace `SkinAnalyzerV3` with `SkinAnalyzer`
- Replace `SkinAnalyzer._core_to_v3` with `SkinAnalyzer._legacy_to_current`

**Timeline**:
- **Deprecated**: 2026-05-24
- **Removal**: v2.0 release (Q3 2026)

### get_db_path_from_env (Moved in v1.0)

The `get_db_path_from_env` function has been moved from `src/cli/execution_history.py` to `src/utils/config.py`.

| Old Location | New Location |
|--------------|-------------|
| `src.cli.execution_history.get_db_path_from_env` | `src.utils.config.get_db_path_from_env` |

**Migration Guide**:
- Update imports: `from src.utils.config import get_db_path_from_env`
- The old location still works but is deprecated

**Timeline**:
- **Moved**: 2026-05-24
- **Old Location Removal**: v2.0 release (Q3 2026)

### Server Config Constants (Deprecated in v1.0, Remove in v2.0)

The following config constants in `src/server/deps.py` are deprecated. Use getter functions instead:

| Deprecated Constant | Getter Function | Warning |
|---------------------|-----------------|---------|
| `config` | `get_config()` | ⚠️ 상수 (warning 불가) |
| `SECRET_KEY` | `get_secret_key()` | ⚠️ 상수 (warning 불가) |
| `ALGORITHM` | `get_algorithm()` | ⚠️ 상수 (warning 불가) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `get_access_token_expire_minutes()` | ⚠️ 상수 (warning 불가) |
| `SERVER_HOST` | `get_server_host()` | ⚠️ 상수 (warning 불가) |
| `SERVER_PORT` | `get_server_port()` | ⚠️ 상수 (warning 불가) |
| `SERVER_URL` | `get_server_url()` | ⚠️ 상수 (warning 불가) |
| `ALLOWED_EXT` | `get_allowed_extensions()` | ⚠️ 상수 (warning 불가) |
| `MAX_UPLOAD_BYTES` | `get_max_upload_bytes()` | ⚠️ 상수 (warning 불가) |
| `ALLOWED_ORIGINS` | `get_allowed_origins()` | ⚠️ 상수 (warning 불가) |
| `MAX_CONCURRENT_JOBS` | `get_max_concurrent_jobs()` | ⚠️ 상수 (warning 불가) |
| `JOB_SEMAPHORE_TIMEOUT_SEC` | `get_job_semaphore_timeout_sec()` | ⚠️ 상수 (warning 불가) |
| `DEFAULT_DB_PATH` | `get_default_db_path()` | ⚠️ 상수 (warning 불가) |
| `SUPABASE_ENABLED` | `get_supabase_enabled()` | ⚠️ 상수 (warning 불가) |
| `SUPABASE_URL` | `get_supabase_url()` | ⚠️ 상수 (warning 불가) |
| `SUPABASE_KEY` | `get_supabase_key()` | ⚠️ 상수 (warning 불가) |
| `SUPABASE_BUCKET` | `get_supabase_bucket()` | ⚠️ 상수 (warning 불가) |
| `MAX_WORKERS` | `get_max_workers()` | ⚠️ 상수 (warning 불가) |
| `CLEANUP_INTERVAL_H` | `get_cleanup_interval_h()` | ⚠️ 상수 (warning 불가) |
| `MAX_JOB_AGE_H` | `get_max_job_age_h()` | ⚠️ 상수 (warning 불가) |
| `BACKUP_INTERVAL_H` | `get_backup_interval_h()` | ⚠️ 상수 (warning 불가) |
| `BACKUP_DIR` | `get_backup_dir()` | ⚠️ 상수 (warning 불가) |

**Migration Guide**:
- Replace constant access with getter function calls
- Example: `SECRET_KEY` → `get_secret_key()`

**Timeline**:
- **Deprecated**: 2026-05-24
- **Removal**: v2.0 release (Q3 2026)

## Future Deprecations

### Potential Future Deprecations

The following items are candidates for deprecation in future versions:

1. **v2 Analyzer Versions**: Analyzer versions with `_v2` suffix may be consolidated
2. **Legacy Measurements**: Old measurement formats (e.g., `measurements_v17`, `measurements_v26`) will be removed
3. **Optional Dependencies**: scikit-image optional import pattern may be removed if no longer needed

## Deprecation Warning Handling

### For Developers

When using deprecated code, you will see `DeprecationWarning` messages:

```python
# Example warning
DeprecationWarning: _compute_overall_score_v2는 v2.0에서 제거될 예정입니다. 대신 _compute_overall_score_legacy를 사용하세요.
```

To see deprecation warnings during development:

```python
import warnings
warnings.simplefilter("always", DeprecationWarning)
```

### For CI/CD

Configure CI to treat deprecation warnings as errors:

```python
# pytest.ini or setup.cfg
filterwarnings = error::DeprecationWarning
```

## Contributing

When adding new features:

1. Avoid creating new aliases unless absolutely necessary
2. If deprecation is needed, follow this policy
3. Update this document with the deprecation details
4. Add appropriate `DeprecationWarning` with clear migration instructions

## Questions

For questions about deprecation policy or migration, please:
- Check this document first
- Review the code comments for specific deprecation warnings
- Contact the development team for clarification
