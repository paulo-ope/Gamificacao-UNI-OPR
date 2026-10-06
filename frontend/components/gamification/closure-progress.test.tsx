import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ClosureProgress } from "./closure-progress";

describe("closure progress", () => {
  it("shows exactly one current step from the actual run status", () => {
    const html = renderToStaticMarkup(<ClosureProgress status="review" />);
    expect(html.match(/aria-current="step"/g)).toHaveLength(1);
    expect(html).toMatch(/aria-current="step"[^]*?Conferência/);
    expect(html.match(/: concluída/g)).toHaveLength(1);
  });
  it("does not imply a workflow stage for a cancelled or absent calculation", () => {
    expect(renderToStaticMarkup(<ClosureProgress status="cancelled" />)).toBe("");
    expect(renderToStaticMarkup(<ClosureProgress />)).toBe("");
  });
});
