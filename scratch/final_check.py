import pathlib

main = pathlib.Path('frontend/src/main.tsx').read_text(encoding='utf-8')
workspaces = ['dashboard', 'repositories', 'architecture', 'flows', 'videos', 'learning', 'generator', 'profile']
for ws in workspaces:
    present = f'workspace === "{ws}"' in main
    print(f'  Workspace [{ws}]: {"OK" if present else "MISSING"}')

route_count = sum(1 for ws in workspaces if f'workspace === "{ws}"' in main)
print(f'Total workspaces: {route_count}/8')

css = pathlib.Path('frontend/src/style.css').read_text(encoding='utf-8')
checks = {
    'Repo explainer theater': 'playingRepoExplainer' in main,
    'Stage video theater': 'playingStageVideoId' in main,
    'Playback speed control': 'videoPlaybackRate' in main,
    'Inline stage video URL': 'stage_id}/video' in main,
    'DQN sidebar panel': 'DQN ADAPTIVE MENTOR' in main,
    'Tutor takeover modal': 'TUTOR TAKEOVER DEMONSTRATION' in main,
    'HTTP 206 streaming': pathlib.Path('backend/media_stream.py').exists(),
    'Node inspector drawer': 'NODE INSPECTOR' in main,
    'Edge inspector': 'EDGE INSPECTOR' in main,
    '5-step pipeline banner': 'Step 1' in main and 'Step 5' in main,
    'btn-watch-video CSS': '.btn-watch-video' in css,
    'btn-primary CSS': '.btn-primary' in css,
    'CSS design tokens': '--bg-primary' in css,
    'Learning stage video_path check': 'stage.video_path' in main,
    'Concept mastery progress bars': 'concept_mastery' in main,
}
print()
for label, ok in checks.items():
    print(f'  {label}: {"OK" if ok else "MISSING"}')
