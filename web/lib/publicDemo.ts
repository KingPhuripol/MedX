/**
 * Slice d1: public demo build (NEXT_PUBLIC_PUBLIC_DEMO=1). Lives in a plain module, not in the
 * "use client" DemoLogin: a server component importing a value from a client module gets a
 * client reference (always truthy), which showed the role picker on every build.
 */
export const PUBLIC_DEMO = process.env.NEXT_PUBLIC_PUBLIC_DEMO === "1";
