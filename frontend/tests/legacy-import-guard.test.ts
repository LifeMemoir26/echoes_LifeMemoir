import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const ROOT = path.resolve(process.cwd());
const TARGETS = [path.join(ROOT, "components"), path.join(ROOT, "lib"), path.join(ROOT, "app")];
const FORBIDDEN = [".reference/echoes_-life-memoir-&-replica/services", "from '../services", "from \"../services"];

function collectFiles(dir: string): string[] {
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  const files: string[] = [];

  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...collectFiles(full));
      continue;
    }
    if (full.endsWith(".ts") || full.endsWith(".tsx")) {
      files.push(full);
    }
  }

  return files;
}

describe("legacy import guard", () => {
  it("does not import forbidden legacy services patterns", () => {
    const files = TARGETS.flatMap((target) => collectFiles(target));
    const violations: string[] = [];

    for (const file of files) {
      const content = fs.readFileSync(file, "utf-8");
      for (const pattern of FORBIDDEN) {
        if (content.includes(pattern)) {
          violations.push(`${path.relative(ROOT, file)} => ${pattern}`);
        }
      }
    }

    expect(violations).toEqual([]);
  });
});
