## 0.10.0 (2025-11-26)

### Feat

- **repo**: add automatic entity<->model mapping via introspection
- **cli**: add search command with filtering options
- **api**: add POST /search endpoint with filtering and pagination
- **svc**: add find() and count() methods to service layer
- **repo**: add find() and count() methods with ApiKeyFilter
- **svc**: add entity_factory parameter for custom entity creation

### Refactor

- **domain**: make ApiKeyEntity a pure protocol without implementation
- **svc**: extract common _verify_key logic into reusable helpers

## 0.9.0 (2025-11-26)

### BREAKING CHANGE

- please ensure that if you use sql repository to check how do you use delete_by_id method, this method now return entity and not boolean who define his existence

### Fix

- **cached**: use full API key hash to prevent key_id-only cache hits

### Refactor

- **svc**: replace entity parameter with direct args in create method
- **svc**: create touch method for simplify code of service
- **domain**: create ensure valid scopes domain method for regroup all verification of scopes

### Perf

- **sql**: remove double call to db for delete method

## 0.8.3 (2025-11-24)

### Fix

- **svc**: update last_used_at on cache hit and add cache behavior tests
- **hasher**: apply consistent 72-byte truncation in bcrypt verify
- **svc**: add jittered verify delay and update tests

### Refactor

- simplify _get_parts exception handling and remove dead code, rework docs
- **domain**: make key_hash Optional in Protocol, add safety assertion

## 0.8.2 (2025-11-20)

### Fix

- **repo**: enforce key id uniqueness for all repository
- **cached**: improve security of cached svc by ensure that api key can authenticate

### Perf

- **cached**: improve cached svc by reduce DB hits (use key_id rather use full entity with repo call), warning maybe less secure

## 0.8.1 (2025-11-19)

### Fix

- **svc**: update method don't update key secret first/last (usefull for rotation)
- **svc**: ApiKeyCreateIn and ApiKeyUpdateIn don't update scopes
- **api**: helper to_out don't send the true id of api key

## 0.8.0 (2025-11-18)

### Feat

- **svc**: add rrd (random response delay) when bad api key is provided for avoid brute force attack

### Fix

- **ci/cd**: codecov publish fail because don't have access to files

## 0.7.3 (2025-11-09)

### Fix

- **ci/cd**: fix(ci/cd): fix ci/cd problem with release (empty commit)

## 0.7.2 (2025-11-09)

### Fix

- **ci/cd**: fix ci/cd problem with release (empty commit)

## 0.7.1 (2025-11-09)

### Fix

- **cached**: cached service update (delete or update method) clear cache key

## 0.7.0 (2025-11-09)

### Feat

- **cli**: add fak (fastapi api key) cli for generate api key (for dotenv), get version

## 0.6.0 (2025-11-08)

### BREAKING CHANGE

- Your SQL database (SQLAlchemy repository) must add "scopes" attributes (List[str]) for work, the old schema name is now ApiKeyMixinV1

### Feat

- add scopes attributes to api keys, service, fastapi

## 0.5.0 (2025-11-02)

### BREAKING CHANGE

- service.create(entity, secret) args breaking, now is service.create(entity, key_id, key_secret)

### Feat

- **svc**: add load_dotenv method to load from .env

### Fix

- **security**: svc verify key method don't detect bad global prefix if startWiths

## 0.4.0 (2025-10-31)

### Feat

- **service**: add cached services using aiocache (agnostic backend)

### Fix

- **deps**: forget to add aiocache to `all` extra

### Refactor

- correction of ty warning after upgrade packages

## 0.3.0 (2025-10-15)

### BREAKING CHANGE

- remove using of api.create_api_key_security, now use only create_depends_api_key
- change signature of domain.init and svc.create and break change sql schema (add key_secret_first String(4) nullable and add key_secret_last String(4) nullable)

### Feat

- **domain**: add first and last key secret for help user
- **api**: added the ability to use an HTTPBearer to comply with the rfc6750 standard
- **mock**: add mock api key hasher for tests purpose

### Fix

- **api**: ensure that security have autoerror=False for respect RFC 9110/7235

### Refactor

- **all**: create specific modules for typing
- **api**: remove depreated function create_api_key_security, update docs

## 0.2.1 (2025-10-13)

### Fix

- **router**: add json schema to deleted 204 response

## 0.2.0 (2025-10-11)

### Feat

- **fastapi**: improve creation of verify key depends (now use Depends)
- **cli**: add typer interface to handle service
- **router**: add activate/deactive routes, improve DI to router/security factory
- **router**: add create api key security for fastapi app
- add fastapi dependencies, add example sqlalchemy router
- add sqlalchemy to optional dependencies
- service create use entity for persistance
- add ensure table, patchfix update/create method of sql repo
- add services, little refactor and add basic tests
- add domain api key hasher protocol/class with tests
- add repository base with sqlalchemy implementation
- add domain api key model
- init project with uv

### Fix

- **factory**: python <3.11 don't support 'z' in datetime.fromisoformat
- **svc**: test verify key expired can failed, fix it
- align create signature with returned tuple
- handle missing api key with 404

### Refactor

- change structure of modules (repo, hasher, api, cli)
- fix import error of optional deps, restructure code, merge file
- clean linter warning and format code
- **hasher**: rework structure of module for check optional install
- add tests for coverage, refactor codex work
- promote utc handling
- rework tests structure, refactor code
- rework optional dependencies group (package, core, fastapi, all)
- move domain/model factory function to static method
- apply mixin pattern to sqlalchemy repo
- apply domain standard nomenclature to all variables
- rename key prefix to key id (domain standard nomenclature)
- rework utils function, and structure of init
