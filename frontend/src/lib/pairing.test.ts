import { describe, expect, it } from "vitest";

import { pairFiles, type DroppedFile } from "./pairing";

function makeFile(relativePath: string): DroppedFile {
  const filename = relativePath.split("/").pop() ?? relativePath;
  return {
    file: new File([new Uint8Array([0])], filename),
    relativePath,
  };
}

describe("pairFiles — flat drop, stem-prefix matching", () => {
  it("pairs each PDF with its stem-prefixed images", () => {
    const result = pairFiles([
      makeFile("widget-001.pdf"),
      makeFile("widget-001-front.png"),
      makeFile("widget-001-back.jpg"),
      makeFile("widget-002.pdf"),
      makeFile("widget-002.png"),
    ]);
    expect(result.items).toHaveLength(2);
    expect(result.orphanPdfs).toHaveLength(0);
    expect(result.orphanImages).toHaveLength(0);
    const firstItem = result.items.find((it) => it.itemId === "widget-001")!;
    expect(firstItem.labels.map((l) => l.relativePath).sort()).toEqual([
      "widget-001-back.jpg",
      "widget-001-front.png",
    ]);
  });

  it("longest-prefix-wins prevents shorter-stem PDF from stealing", () => {
    const result = pairFiles([
      makeFile("widget.pdf"),
      makeFile("widget-2.pdf"),
      makeFile("widget-2-front.png"),
      makeFile("widget-front.png"),
    ]);
    const longerItem = result.items.find((it) => it.itemId === "widget-2")!;
    const shorterItem = result.items.find((it) => it.itemId === "widget")!;
    expect(longerItem.labels.map((l) => l.relativePath)).toEqual(["widget-2-front.png"]);
    expect(shorterItem.labels.map((l) => l.relativePath)).toEqual(["widget-front.png"]);
  });

  it("image with no matching PDF stem becomes an orphan image", () => {
    const result = pairFiles([
      makeFile("widget.pdf"),
      makeFile("widget-front.png"),
      makeFile("unrelated.png"),
    ]);
    expect(result.items).toHaveLength(1);
    expect(result.orphanImages.map((i) => i.relativePath)).toEqual(["unrelated.png"]);
  });

  it("PDF with no matching images becomes an orphan PDF", () => {
    const result = pairFiles([makeFile("alone.pdf"), makeFile("other.pdf"), makeFile("other-front.png")]);
    expect(result.items).toHaveLength(1);
    expect(result.items[0].itemId).toBe("other");
    expect(result.orphanPdfs.map((p) => p.relativePath)).toEqual(["alone.pdf"]);
  });
});

describe("pairFiles — folder-as-form rule", () => {
  it("emits one item per subfolder when subfolder has exactly one PDF and >=1 image", () => {
    const result = pairFiles([
      makeFile("batch/widget-001/form.pdf"),
      makeFile("batch/widget-001/front.png"),
      makeFile("batch/widget-001/back.png"),
      makeFile("batch/widget-002/form.pdf"),
      makeFile("batch/widget-002/wrap.png"),
    ]);
    expect(result.items).toHaveLength(2);
    expect(result.orphanPdfs).toHaveLength(0);
    expect(result.orphanImages).toHaveLength(0);
  });

  it("subfolder with 2+ PDFs falls through to stem matching", () => {
    const result = pairFiles([
      makeFile("batch/widget-a.pdf"),
      makeFile("batch/widget-b.pdf"),
      makeFile("batch/widget-a-front.png"),
      makeFile("batch/widget-b-back.png"),
    ]);
    expect(result.items).toHaveLength(2);
    const a = result.items.find((it) => it.itemId === "widget-a")!;
    const b = result.items.find((it) => it.itemId === "widget-b")!;
    expect(a.labels.map((l) => l.relativePath)).toEqual(["batch/widget-a-front.png"]);
    expect(b.labels.map((l) => l.relativePath)).toEqual(["batch/widget-b-back.png"]);
  });

  it("subfolder with PDF only (no images) yields orphan PDF", () => {
    const result = pairFiles([makeFile("batch/lonely/form.pdf")]);
    expect(result.items).toHaveLength(0);
    expect(result.orphanPdfs).toHaveLength(1);
  });
});

describe("pairFiles — flagging and validation", () => {
  it("flags items with more than 10 matched labels", () => {
    const files = [makeFile("widget.pdf")];
    for (let i = 0; i < 11; i++) {
      files.push(makeFile(`widget-${i}.png`));
    }
    const result = pairFiles(files);
    expect(result.items).toHaveLength(1);
    expect(result.items[0].labels).toHaveLength(11);
    expect(result.items[0].isOverLabelLimit).toBe(true);
  });

  it("filters unsupported extensions into ignoredFiles", () => {
    const result = pairFiles([
      makeFile("widget.pdf"),
      makeFile("widget-front.png"),
      makeFile("notes.txt"),
      makeFile("data.csv"),
    ]);
    expect(result.ignoredFiles.map((f) => f.relativePath).sort()).toEqual(["data.csv", "notes.txt"]);
    expect(result.items).toHaveLength(1);
  });

  it("dedupes duplicate item IDs across buckets with -2/-3 suffix", () => {
    const result = pairFiles([
      makeFile("a/widget.pdf"),
      makeFile("a/widget-front.png"),
      makeFile("b/widget.pdf"),
      makeFile("b/widget-back.png"),
    ]);
    const ids = result.items.map((it) => it.itemId).sort();
    expect(ids).toEqual(["widget", "widget-2"]);
  });
});
