# Hermes Course Authoring and Interactive Teaching

## Problem Statement

The user wants to use OpenMAIC-style capabilities entirely through conversation with Hermes Agent. They do not want to run OpenMAIC in Docker or open a separate OpenMAIC application. They need Hermes to design courses, generate teaching content, conduct an interactive lesson, run exercises, remember progress, and export reusable course artifacts.

OpenMAIC is used as a source of architectural and implementation reference. Its pure, dependency-light packages are ported or vendored where they provide tested domain behavior: `@openmaic/dsl` and `@openmaic/generation`, plus selected pure quiz, orchestration, prompt, PBL, and export helpers. Its browser application and deployment stack are not runtime dependencies of the Hermes capability.

## Solution

Implement a native, user-local Hermes course-authoring capability. Hermes remains the conversational front end and orchestrator. A local course-authoring package provides a small, deep interface for course lifecycle operations, while Hermes existing tools provide web research, file access, image generation, TTS, delegation, and artifact delivery.

The capability supports two interaction modes:

1. **Authoring mode** — design, generate, revise, inspect, and export a course.
2. **Classroom mode** — teach the course in the current conversation, ask questions, conduct exercises, grade answers, adapt pacing, and track progress.

Complex browser-like interactions are delivered as standalone HTML artifacts. Telegram remains the primary conversational and delivery surface.

## User Stories

1. As a learner, I want to request a course from a topic so that I can start learning without opening another application.
2. As a learner, I want to provide a target audience, duration, difficulty, language, and goals so that the course fits my needs.
3. As a learner, I want to use documents, audio, video, and URLs as source material so that the course reflects my materials.
4. As a course author, I want Hermes to produce learning objectives and prerequisites so that the course has a coherent teaching contract.
5. As a course author, I want Hermes to generate a multi-lesson outline so that the course has structure and progression.
6. As a course author, I want each lesson to contain explanation, examples, visuals, exercises, and assessment so that it is teachable rather than only descriptive.
7. As a course author, I want to revise one lesson or scene without regenerating the whole course so that iteration is efficient.
8. As a course author, I want to add, delete, duplicate, reorder, and rename lessons so that I can control the course structure.
9. As a learner, I want Hermes to teach one lesson at a time so that the conversation remains manageable.
10. As a learner, I want to ask questions during a lesson so that teaching adapts to my confusion.
11. As a learner, I want an AI teacher to explain concepts in a selected style so that the delivery matches my preference.
12. As a learner, I want AI classmates or assistants to provide alternative viewpoints so that the lesson feels interactive.
13. As a learner, I want discussions and debates around a topic so that I can compare perspectives.
14. As a learner, I want Hermes to use whiteboard-style diagrams and generated images when useful so that abstract material becomes visual.
15. As a learner, I want voice narration when appropriate so that I can listen instead of reading everything.
16. As a learner, I want quizzes and short-answer exercises so that I can check understanding.
17. As a learner, I want immediate grading and explanations so that mistakes become learning opportunities.
18. As a learner, I want Hermes to record weak areas so that later lessons can adapt to my needs.
19. As a learner, I want project-based tasks with milestones so that I can apply the material.
20. As a learner, I want to pause, resume, or restart a course so that progress is not lost.
21. As a learner, I want Hermes to remember course progress across conversations so that I do not need to repeat my position.
22. As a course author, I want a teacher version and a student version so that answers and instructor notes can be separated.
23. As a course author, I want Markdown export so that the course is easy to inspect and edit.
24. As a course author, I want PDF export so that the course can be read or printed.
25. As a course author, I want editable PPTX export so that slides can be reused.
26. As a learner, I want a standalone interactive HTML export so that simulations can run without OpenMAIC.
27. As a course author, I want a portable course ZIP so that the course can be archived or shared.
28. As a Telegram user, I want generated files delivered directly in chat so that I do not need to open another application.
29. As a user, I want Hermes to ask for approval before external side effects such as sending messages or controlling devices so that course generation remains safe.
30. As a user, I want failures in one media provider or export format to degrade gracefully so that the core course remains usable.

## Implementation Decisions

- Hermes is the primary runtime, conversational surface, orchestrator, and delivery channel.
- OpenMAIC is a reference source only; the implementation must not import or start OpenMAIC at runtime.
- The capability is implemented as a user-local Hermes skill plus a local supporting package/scripts. It is not a new always-present core model tool.
- The skill exposes conversational commands through natural language and uses existing Hermes tools rather than duplicating web, file, image, audio, or delegation infrastructure.
- Course state is stored as versioned JSON plus human-readable Markdown under a user-configurable course workspace. The default uses the active Hermes home/profile safely and never hardcodes another profile.
- The canonical domain model contains Course, Lesson, Scene, Exercise, Assessment, ClassroomSession, ProgressRecord, and ArtifactManifest.
- A course is generated in stages: requirements, outline, lesson content, exercises, media references, validation, and export.
- Each lesson is independently versioned. Revisions target a lesson or scene and preserve prior versions.
- Classroom mode uses a state machine with explicit states: ready, teaching, awaiting_answer, discussing, reviewing, paused, completed, and failed.
- The classroom director may use Hermes delegation for independent teacher/peer perspectives, but it must preserve message alternation and avoid recursive course-agent invocation.
- Web research is opt-in per course request and must retain source URLs in the course manifest.
- Generated media is optional. Missing media must not prevent Markdown or text lesson delivery.
- Interactive HTML is self-contained where possible and must report assets that could not be embedded.
- PPTX/PDF/HTML/ZIP exporters are adapters behind one export interface. Unsupported or unavailable exporters return structured errors without corrupting the course.
- Telegram delivery uses Hermes's existing media/file delivery path. The skill returns absolute artifact paths for delivery; it does not implement a second messaging client.
- Secrets remain in Hermes's configured secret store/environment. Course settings and feature flags are configuration, not secrets.
- No OpenMAIC Docker, PostgreSQL, Next.js server, or browser UI is required.
- Existing OpenMAIC integration changes that only point Docker at the Hermes proxy are not part of this implementation and should not be required for the native capability.

## Testing Decisions

- Test through the highest seams: domain lifecycle, classroom state transitions, content validation, and exporter interfaces.
- Tests assert external behavior and invariants rather than implementation details or current model lists.
- Use deterministic fake model/research/media adapters for unit tests; never use live network in unit tests.
- Add integration tests with a temporary Hermes home/course workspace to verify path resolution, persistence, resume, and artifact delivery paths.
- Add fixture-based tests for Markdown, JSON, HTML, PPTX, and ZIP outputs where those exporters are available.
- Exercise failure paths: malformed model output, missing source material, unavailable media provider, invalid answer, cancellation, timeout, and partial export.
- Add an end-to-end smoke test that starts with a natural-language course request, creates a course, teaches one lesson, grades one exercise, resumes the session, and exports at least Markdown and one binary artifact.
- Follow existing Hermes skill tests and local Python/TypeScript test conventions discovered during implementation.

## Out of Scope

- Reproducing the full OpenMAIC browser classroom UI inside Hermes.
- Running OpenMAIC Docker, its Next.js app, or its database runtime.
- Reimplementing every OpenMAIC visual animation exactly.
- Automatically exposing terminal, filesystem write, messaging, Home Assistant, or other high-risk Hermes tools to classroom agents.
- Replacing Hermes's core agent loop or adding a permanently loaded core model tool.
- Building a public multi-user SaaS course platform.
- Automatic publication to external learning management systems.
- Unattended external communication or device control.

## Further Notes

The first implementation should prioritize a reliable text-first course workflow and then add media/export adapters. The feature is complete only when the conversational path works without opening OpenMAIC and the generated course can be resumed and delivered from Hermes.
