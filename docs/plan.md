# Implementation Plan: Hermes Course Authoring

## 0. Baseline and safety

- Preserve the existing Hermes skill tree using the user's required external backup procedure before any skill-tree write.
- Inspect the current Hermes profile, skill conventions, artifact-delivery conventions, and available export dependencies.
- Inspect OpenMAIC source modules for domain behavior and license-compatible reference material.
- Keep the unrelated OpenMAIC Docker bridge changes isolated and do not make them a prerequisite.
- Acceptance: baseline paths, branch/state, backup path, and dependency availability are recorded.

## 1. OpenMAIC core port

- Vendor or install the pure `@openmaic/dsl` and `@openmaic/generation` packages from the OpenMAIC repository.
- Port the prompt corpus, JSON repair/retry, outline generation, scene generation, and schema validation behind an injectable Hermes `AICallFn`.
- Port pure quiz grading and PBL kernels; keep browser/UI, Zustand, Next.js routes, video rendering, and database-specific adapters out of the runtime.
- Acceptance: Hermes can create a schema-valid OpenMAIC-compatible outline and lesson scene using a fake injected model, with no Next.js or browser imports.

## 2. Native capability seam

- Create a user-local `course-authoring` skill with concise trigger, workflow, safety rules, and verification steps.
- Create a local supporting package under the skill directory with a small interface for course lifecycle, classroom lifecycle, validation, and export.
- Keep model, research, media, delegation, persistence, and delivery dependencies injectable.
- Acceptance: the skill can be loaded and describes a complete natural-language workflow without requiring OpenMAIC.

## 2. Domain model and persistence

- Implement typed/validated Course, Lesson, Scene, Exercise, Assessment, Progress, ClassroomSession, and ArtifactManifest structures.
- Implement versioned JSON and Markdown persistence with atomic writes and profile-safe workspace resolution.
- Implement create, read, update, list, resume, and archive operations.
- Acceptance: a course survives process restart and a second Hermes conversation can resume it.

## 3. Course design and lesson generation

- Implement a deterministic orchestration contract for requirements, outline, lesson, exercise, and validation stages.
- Add prompt templates that return schema-valid JSON, with repair/rejection handling.
- Support revision at course, lesson, scene, and exercise level without destroying history.
- Acceptance: a topic produces a multi-lesson course and a targeted revision changes only the requested scope.

## 4. Classroom director

- Implement the classroom state machine and conversational turn contract.
- Support lecture, question answering, discussion, peer perspectives, review, pause, resume, and completion.
- Use Hermes existing delegation only for bounded independent perspectives; prevent recursion and unsafe tools.
- Persist current lesson, turn, answer state, and progress after each meaningful transition.
- Acceptance: one course can be taught over multiple messages, paused, resumed, and completed with progress intact.

## 5. Exercises and assessment

- Implement choice, multi-choice, short-answer, scenario, code/task, and milestone exercise types.
- Implement grading rubrics, feedback, confidence/partial credit, weak-area tracking, and remedial recommendations.
- Acceptance: valid, invalid, and partial answers produce deterministic structured feedback and update progress.

## 6. Research and media adapters

- Connect web research through existing Hermes web tools and preserve citations in the course manifest.
- Connect optional image generation, TTS, and whiteboard/diagram generation through existing Hermes capabilities.
- Implement graceful degradation when a provider is unavailable.
- Acceptance: a researched lesson contains source references; media failures leave a usable text-first lesson.

## 7. Exporters and Telegram delivery

- Implement Markdown and JSON exports first.
- Add standalone self-contained HTML for interactive lessons.
- Add PDF and PPTX adapters using available local libraries or deterministic external commands already present on the host.
- Add portable ZIP with manifest, source, assets, and integrity metadata.
- Return absolute artifact paths in the format Hermes can deliver through Telegram.
- Acceptance: Markdown and JSON always work; each optional exporter either produces a verified artifact or a structured capability error.

## 8. Skill integration and user workflow

- Wire the skill to natural-language intents: design, build, teach, quiz, revise, resume, export, list, and archive.
- Document examples in the skill and ensure no user-facing setup requires Docker or another app.
- Add safety prompts/approval requirements for external side effects and large/costly generation.
- Acceptance: the user can complete the core lifecycle entirely in Telegram.

## 9. Verification and hardening

- Run unit tests, integration tests with temporary Hermes home, exporter fixtures, and a real smoke test.
- Run skill validation and inspect the final diff for secrets, profile-crossing paths, and unintended Docker changes.
- Verify generated artifacts by reopening/parsing them, not merely checking that a command returned zero.
- Run a code/spec review and fix all blocking findings.
- Acceptance: all required tests and the conversational smoke test pass with recorded real output.

## Execution order

1. Baseline/backup and source inspection.
2. Skill seam plus domain model/persistence.
3. Course design and lesson generation.
4. Classroom director and exercises.
5. Research/media adapters.
6. Exporters and delivery.
7. Integration, verification, and cleanup.

## Explicit decision gate

Before adding heavyweight PPTX/PDF or browser-like HTML behavior, the text-first course lifecycle must pass its end-to-end smoke test. This prevents building exporters around an unstable course model.
