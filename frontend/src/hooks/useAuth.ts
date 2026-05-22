import { useAppSelector, useAppDispatch } from "@/store/hooks"
import { logout } from "@/store/slices/authSlice"

export function useAuth() {
  const auth = useAppSelector((state) => state.auth)
  const dispatch = useAppDispatch()

  return {
    ...auth,
    logout: () => dispatch(logout()),
  }
}
