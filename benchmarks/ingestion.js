import http from 'k6/http';
import { check } from 'k6';
import { Counter } from 'k6/metrics';

const accepted = new Counter('events_accepted');
const backpressure = new Counter('backpressure_responses');
const mode = __ENV.SCENARIO || 'sustained';
const rate = Number(__ENV.RATE || 20);
const duration = __ENV.DURATION || '30s';
const scenarios = {
  ingestion: { executor: 'constant-vus', vus: 1, duration },
  concurrent: { executor: 'constant-vus', vus: Number(__ENV.VUS || 10), duration },
  sustained: { executor: 'constant-arrival-rate', rate, timeUnit: '1s', duration, preAllocatedVUs: 10, maxVUs: 100 },
  burst: { executor: 'ramping-arrival-rate', startRate: 1, timeUnit: '1s', preAllocatedVUs: 10, maxVUs: 100,
    stages: [{ target: rate, duration: '5s' }, { target: rate * 4, duration: '10s' }, { target: 1, duration: '10s' }] },
  backpressure: { executor: 'constant-arrival-rate', rate: rate * 5, timeUnit: '1s', duration, preAllocatedVUs: 20, maxVUs: 100 },
};
if (!(mode in scenarios)) throw new Error('Unsupported SCENARIO');
export const options = {
  scenarios: { [mode]: scenarios[mode] },
  summaryTrendStats: ['avg', 'min', 'med', 'p(95)', 'p(99)', 'max'],
  thresholds: { checks: ['rate>0.99'] },
};

export default function () {
  const response = http.post(`${__ENV.BASE_URL}/api/events`, JSON.stringify({
    project_id: __ENV.PROJECT_ID,
    type: `benchmark.${__ENV.RUN_ID}`,
    payload: { run_id: __ENV.RUN_ID, vu: __VU, iteration: __ITER, bytes: 'x'.repeat(256) },
  }), { headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${__ENV.API_KEY}`,
    'Idempotency-Key': `${__ENV.RUN_ID}-${__VU}-${__ITER}` }, tags: { name: 'ingest_event' } });
  if (response.status === 201) accepted.add(1);
  if (response.status === 429 || response.status === 503) backpressure.add(1);
  check(response, { 'accepted or explicit backpressure': r => r.status === 201 || r.status === 429 || r.status === 503 });
}

export function handleSummary(data) {
  return { [__ENV.SUMMARY_PATH || '/results/k6-summary.json']: JSON.stringify(data, null, 2) };
}
