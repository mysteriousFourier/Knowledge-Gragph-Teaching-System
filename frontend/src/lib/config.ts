export interface RuntimeConfig {
  educationApiBaseUrl: string
  maintenanceApiBaseUrl: string
  backendAdminBaseUrl: string
}

export function getRuntimeConfig(): RuntimeConfig {
  const appConfig = (window as unknown as { __APP_CONFIG__?: Partial<RuntimeConfig> }).__APP_CONFIG__
  const origin = window.location.origin

  return {
    educationApiBaseUrl: appConfig?.educationApiBaseUrl || origin,
    maintenanceApiBaseUrl: appConfig?.maintenanceApiBaseUrl || origin,
    backendAdminBaseUrl: appConfig?.backendAdminBaseUrl || origin,
  }
}
