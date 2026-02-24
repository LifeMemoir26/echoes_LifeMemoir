import fs from "node:fs";
import path from "node:path";

const frontendDocPath = path.resolve("./API_INTEGRATION.md");
const backendModelsPath = path.resolve("../backend/src/app/api/v1/models.py");

function assertContains(content, needle, from) {
  if (!content.includes(needle)) {
    throw new Error(`Missing contract field \"${needle}\" in ${from}`);
  }
}

const frontendDoc = fs.readFileSync(frontendDocPath, "utf8");
const backendModels = fs.readFileSync(backendModelsPath, "utf8");

const requestFields = ["username", "target_length", "user_preferences", "auto_save"];
const responseFields = ["memoir", "length", "generated_at", "trace_id"];
const errorFields = ["error_code", "error_message", "retryable", "trace_id"];

for (const field of requestFields) {
  assertContains(frontendDoc, field, "frontend/API_INTEGRATION.md");
  assertContains(backendModels, field, "backend/src/app/api/v1/models.py");
}

for (const field of responseFields) {
  assertContains(frontendDoc, field, "frontend/API_INTEGRATION.md");
  assertContains(backendModels, field, "backend/src/app/api/v1/models.py");
}

for (const field of errorFields) {
  assertContains(frontendDoc, field, "frontend/API_INTEGRATION.md");
  assertContains(backendModels, field, "backend/src/app/api/v1/models.py");
}

console.log("Contract parity check passed.");
