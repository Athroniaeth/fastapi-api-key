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
