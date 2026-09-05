import { createFileRoute, redirect } from "@tanstack/react-router"

/** Canonical teacher console lives at /teacher; keep this URL as a compatibility alias. */
export const Route = createFileRoute("/teacher/courses")({
  beforeLoad: () => {
    throw redirect({ to: "/teacher" })
  },
})
