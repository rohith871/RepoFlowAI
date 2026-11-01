import React from "react";
import { Composition } from "remotion";
import { RepoFlowVideo } from "./RepoFlowComposition";
import type { RepoFlowCompositionProps } from "./types";

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="RepoFlowLesson"
      component={RepoFlowVideo as any}
      durationInFrames={300}
      fps={30}
      width={1920}
      height={1080}
      defaultProps={{
        lesson_id: "default_lesson",
        title: "RepoFlow AI Architecture Walkthrough",
        repository_id: "repo",
        scenes: [],
      }}
      calculateMetadata={({ props }: { props: RepoFlowCompositionProps }) => {
        const fps = 30;
        const totalDurationMs =
          props?.scenes?.reduce((acc, s) => acc + (s.duration_ms || 6000), 0) || 6000;
        const durationInFrames = Math.max(30, Math.round((totalDurationMs / 1000) * fps));
        return {
          durationInFrames,
          fps,
          width: 1920,
          height: 1080,
        };
      }}
    />
  );
};
