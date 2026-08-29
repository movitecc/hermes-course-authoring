# Hermes Course Authoring

OpenMAIC-inspired course design, interactive teaching, assessment, PBL, and artifact export as a native Hermes Agent capability.

This repository does **not** run OpenMAIC, Docker, Next.js, or a browser classroom application. Hermes is the conversational runtime; the vendored OpenMAIC packages provide portable course DSL and generation behavior.

## Layout

- `skill/` — installable Hermes `course-authoring` skill and persistence engine.
- `core/bin/` — Hermes-compatible adapters for outline, scene, and PBL generation.
- `vendor/openmaic-core/packages/@openmaic/dsl/` — portable OpenMAIC DSL.
- `vendor/openmaic-core/packages/@openmaic/generation/` — portable OpenMAIC generation package and prompts.
- `docs/spec.md` — product specification.
- `docs/plan.md` — implementation plan.

## Local verification

```bash
cd vendor/openmaic-core
npm install --ignore-scripts
npm run build
./node_modules/.bin/vitest run packages/@openmaic/dsl/test
./node_modules/.bin/vitest run packages/@openmaic/generation/test --exclude packages/@openmaic/generation/test/pbl-planner.test.ts
python3 ../../skill/scripts/course_authoring.py --help
```

The excluded upstream test checks an OpenMAIC app compatibility barrel that is intentionally not included in this standalone repository.

## Hermes installation

Copy `skill/` to the active profile's skills directory as `productivity/course-authoring`, or install the repository through the user's normal Hermes skill workflow. Supporting adapters are kept in `core/` and can be invoked from the skill's scripts directory after installation.

## License

The original OpenMAIC source packages retain their upstream MIT license files. New repository glue is MIT licensed.
