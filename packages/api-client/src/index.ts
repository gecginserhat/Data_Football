/**
 * Kurgu API istemcisi. Tipler FastAPI OpenAPI şemasından üretilir (`make openapi`).
 * Elle düzenlemeyin: `src/schema.d.ts` üretilmiş dosyadır.
 */
import createClient, { type ClientOptions } from "openapi-fetch";
import type { components, paths } from "./schema";

export type { components, paths };
export type Schemas = components["schemas"];
export type Me = Schemas["MeOut"];

export const TENANT_HEADER = "X-Kurgu-Tenant";

export function createKurguClient(options: ClientOptions) {
  return createClient<paths>(options);
}

export type KurguClient = ReturnType<typeof createKurguClient>;
