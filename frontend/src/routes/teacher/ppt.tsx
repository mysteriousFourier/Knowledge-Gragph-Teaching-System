import { createFileRoute, redirect } from "@tanstack/react-router"

export const Route = createFileRoute("/teacher/ppt")({
  beforeLoad: () => {
    throw redirect({ to: "/teacher/prepare", search: { chapterId: "", nodeId: "" } })
  },
})
