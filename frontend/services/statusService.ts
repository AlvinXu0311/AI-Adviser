import { apiFetch } from './apiClient';

export interface StatusComponent {
  key: string;
  label: string;
  status: 'online' | 'offline';
  details: string;
}

export interface SystemStatus {
  overall_status: 'online' | 'degraded';
  timestamp: string;
  components: StatusComponent[];
}

export async function getSystemStatus(): Promise<SystemStatus> {
  const res = await apiFetch('/api/status', { method: 'GET' });

  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`Status request failed: ${res.status} ${text}`);
  }

  return res.json();
}

export default {
  getSystemStatus,
};
