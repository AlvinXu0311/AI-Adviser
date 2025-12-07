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

// Use empty string for Docker (nginx proxy), or localhost for local dev
const API_BASE_URL = (import.meta.env.VITE_BACKEND_URL !== undefined 
  ? import.meta.env.VITE_BACKEND_URL 
  : 'http://localhost:8000').replace(/\/$/, '');

export async function getSystemStatus(): Promise<SystemStatus> {
  const res = await fetch(`${API_BASE_URL}/api/status`, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
  });

  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`Status request failed: ${res.status} ${text}`);
  }

  return res.json();
}

export default {
  getSystemStatus,
};
