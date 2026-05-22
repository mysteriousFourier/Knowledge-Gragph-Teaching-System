import { createRootRoute, Outlet } from "@tanstack/react-router"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { Provider as ReduxProvider } from "react-redux"
import { store } from "@/store"
import { AppLayout } from "@/components/layout/AppLayout"
import { SettingsPanel } from "@/components/layout/SettingsPanel"

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

export const Route = createRootRoute({
  component: RootComponent,
})

function RootComponent() {
  return (
    <ReduxProvider store={store}>
      <QueryClientProvider client={queryClient}>
        <AppLayout>
          <Outlet />
        </AppLayout>
        <SettingsPanel />
      </QueryClientProvider>
    </ReduxProvider>
  )
}
