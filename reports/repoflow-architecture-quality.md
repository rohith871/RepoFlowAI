# RepoFlow AI Architecture Explainer Quality Report

## Verified local render

- Repository: `fixtures/sample_project`
- Repository ID: `repo_df8326fc4a0c1b3bdf4f`
- Graph result: 6 symbols and 3 verified relationships
- Scope: repository
- Detail: summary
- Storyboard provider: `deterministic-evidence-storyboard`
- Narration: Pocket TTS `alba`
- Actual duration: 116.4 seconds
- Output: `reports/repoflow-architecture-explainer.mp4`
- Inspection artifact: `reports/repoflow-architecture-contact-sheet.png`

## Verified public-repository render

- Repository: `psf/requests`
- Repository ID: `repo_0d1a89c543bad402b2da`
- Imported analysis: 127 files, 844 symbols, 96 relationships, 1,360 facts, and 1,491 evidence records.
- Graph API result: 250 nodes returned by the API limit and 35 relationships in the returned graph window.
- Scope: repository
- Detail: summary
- Storyboard provider: `deterministic-evidence-storyboard`
- Actual duration: 262 seconds
- Output: `reports/repoflow-psf-requests-explainer.mp4`
- Inspection artifact: `reports/repoflow-psf-requests-contact-sheet.png`
- The public-repository contact sheet contains nine frames sampled across the 262-second render, including code highlighting and directional flow scenes.

## Visual checks performed

- The architecture scene progressively reveals actual graph nodes and directional edges.
- Flow scenes show directional connections and moving yellow data packets.
- Code scenes use repository excerpts, source paths, line ranges, and progressive line highlighting.
- Frame extraction produced three representative PNG frames.
- The generated MP4 decoded successfully with FFmpeg.
- Audio and video stream validation passed.
- Captions and chapter boundaries were generated from measured Pocket TTS segment durations.

## Provider status

- Groq routing is implemented as the primary provider when `GROQ_API_KEY` is configured.
- The key was not present in this validation environment, so no live Groq request was claimed.
- The Ollama HTTP endpoint was unavailable in this validation environment.
- The `ollama` executable was also unavailable in the container, so installed local model tags could not be independently enumerated here.
- The configured fallback tag is `qwen2.5-coder:7b`.
- With both providers unavailable, the rendered result explicitly records the deterministic storyboard provider.

## Remaining limitations

- Remotion is not integrated. The existing Pillow + FFmpeg pipeline was upgraded in place to preserve the working media stack and avoid adding an unverified rendering runtime.
- The current visual system is deterministic frame animation rather than a full React/Remotion composition engine.
- Groq and local Ollama require user-side configuration and availability for provider-backed narration/storyboard overlays.
- Word-level TTS timestamps are not available; synchronization is sentence/scene-level using measured audio segment durations.
