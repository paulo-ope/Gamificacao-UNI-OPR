import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Field } from "./field";
import { Input } from "./input";
import { Label } from "./label";
import { Select } from "./select";

describe("accessible fields", () => {
  it("associates each repeated field with its own unique control", () => {
    const html = renderToStaticMarkup(<>{[1, 2].map((item) => <Field key={item}><Label>Nome</Label><Input defaultValue={String(item)} /></Field>)}</>);
    const labels = Array.from(html.matchAll(/for="([^"]+)"/g), (match) => match[1]);
    const controls = Array.from(html.matchAll(/<input[^>]*id="([^"]+)"/g), (match) => match[1]);
    expect(labels).toEqual(controls);
    expect(new Set(labels).size).toBe(2);
  });
  it("preserves an explicit label, ID, disabled state and selected value", () => {
    const html = renderToStaticMarkup(<Field><Label htmlFor="status">Status</Label><Select id="status" defaultValue="paid" disabled><option value="draft">Rascunho</option><option value="paid">Pago</option></Select></Field>);
    expect(html).toContain('for="status"');
    expect(html).toContain('id="status"');
    expect(html).toContain('disabled=""');
    expect(html).toContain('value="paid" selected=""');
  });
});
