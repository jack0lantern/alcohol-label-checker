export type DroppedFile = {
  file: File;
  relativePath: string;
};

export type PairedItem = {
  itemId: string;
  pdf: DroppedFile;
  labels: DroppedFile[];
  isOverLabelLimit: boolean;
};

export type PairingResult = {
  items: PairedItem[];
  orphanPdfs: DroppedFile[];
  orphanImages: DroppedFile[];
  ignoredFiles: DroppedFile[];
};

const PDF_EXTENSIONS = new Set([".pdf"]);
const IMAGE_EXTENSIONS = new Set([".png", ".jpg", ".jpeg", ".webp"]);

function getFilename(relativePath: string): string {
  const slashIndex = relativePath.lastIndexOf("/");
  return slashIndex >= 0 ? relativePath.slice(slashIndex + 1) : relativePath;
}

function getExtension(filename: string): string {
  const dotIndex = filename.lastIndexOf(".");
  return dotIndex >= 0 ? filename.slice(dotIndex).toLowerCase() : "";
}

function getStem(filename: string): string {
  const dotIndex = filename.lastIndexOf(".");
  return dotIndex >= 0 ? filename.slice(0, dotIndex) : filename;
}

function getParentPath(relativePath: string): string {
  const slashIndex = relativePath.lastIndexOf("/");
  return slashIndex >= 0 ? relativePath.slice(0, slashIndex) : "";
}

function isPdf(file: DroppedFile): boolean {
  return PDF_EXTENSIONS.has(getExtension(getFilename(file.relativePath)));
}

function isImage(file: DroppedFile): boolean {
  return IMAGE_EXTENSIONS.has(getExtension(getFilename(file.relativePath)));
}

export function pairFiles(input: DroppedFile[]): PairingResult {
  const ignoredFiles: DroppedFile[] = [];
  const supported: DroppedFile[] = [];
  for (const f of input) {
    if (isPdf(f) || isImage(f)) {
      supported.push(f);
    } else {
      ignoredFiles.push(f);
    }
  }

  const buckets = new Map<string, DroppedFile[]>();
  for (const f of supported) {
    const parent = getParentPath(f.relativePath);
    const list = buckets.get(parent) ?? [];
    list.push(f);
    buckets.set(parent, list);
  }

  const items: PairedItem[] = [];
  const orphanPdfs: DroppedFile[] = [];
  const orphanImages: DroppedFile[] = [];

  for (const [bucketKey, bucketFiles] of buckets.entries()) {
    const pdfs = bucketFiles.filter(isPdf);
    const images = bucketFiles.filter(isImage);

    // Folder-as-form rule: only applies when files are in a named subfolder
    if (bucketKey !== "" && pdfs.length === 1 && images.length >= 1) {
      items.push(makeItem(pdfs[0], images));
      continue;
    }

    // Stem-prefix matching with longest-prefix-wins
    const slots = pdfs.map((pdf) => ({ pdf, labels: [] as DroppedFile[] }));
    for (const image of images) {
      const imageStem = getStem(getFilename(image.relativePath));
      let bestSlot: { pdf: DroppedFile; labels: DroppedFile[] } | null = null;
      let bestStemLength = -1;
      let tied = false;
      for (const slot of slots) {
        const pdfStem = getStem(getFilename(slot.pdf.relativePath));
        if (imageStem.startsWith(pdfStem)) {
          if (pdfStem.length > bestStemLength) {
            bestSlot = slot;
            bestStemLength = pdfStem.length;
            tied = false;
          } else if (pdfStem.length === bestStemLength) {
            tied = true;
          }
        }
      }
      if (bestSlot !== null && !tied) {
        bestSlot.labels.push(image);
      } else {
        orphanImages.push(image);
      }
    }

    for (const slot of slots) {
      if (slot.labels.length === 0) {
        orphanPdfs.push(slot.pdf);
      } else {
        items.push(makeItem(slot.pdf, slot.labels));
      }
    }
  }

  // Deduplicate item IDs
  const seenIds = new Set<string>();
  for (const item of items) {
    const baseId = item.itemId;
    let candidate = baseId;
    let suffix = 1;
    while (seenIds.has(candidate)) {
      suffix += 1;
      candidate = `${baseId}-${suffix}`;
    }
    item.itemId = candidate;
    seenIds.add(candidate);
  }

  return { items, orphanPdfs, orphanImages, ignoredFiles };
}

function makeItem(pdf: DroppedFile, labels: DroppedFile[]): PairedItem {
  const stem = getStem(getFilename(pdf.relativePath));
  return {
    itemId: stem,
    pdf,
    labels,
    isOverLabelLimit: labels.length > 10,
  };
}
