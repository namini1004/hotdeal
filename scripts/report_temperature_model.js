#!/usr/bin/env node
const deals = require('../api/_lib/deals.js');

const SOURCE_LABELS = {
  ppomppu: '뽐뿌',
  quasar: '퀘이사존',
  fmkorea: '펨코',
  ruliweb: '루리웹',
};

function percentile(values = [], fraction = 0.5) {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const position = Math.max(0, Math.min(sorted.length - 1, (sorted.length - 1) * fraction));
  const lower = Math.floor(position);
  const upper = Math.ceil(position);
  if (lower === upper) return sorted[lower];
  const weight = position - lower;
  return sorted[lower] + (sorted[upper] - sorted[lower]) * weight;
}

function mean(values = []) {
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0;
}

function formatNumber(value, digits = 0) {
  return Number(value || 0).toLocaleString('ko-KR', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function sourceLabel(source) {
  return SOURCE_LABELS[source] || source;
}

function normalizeRows(rows = []) {
  return rows.map((row) => ({
    ...row,
    registeredAt: row.registered_at,
    commentSignalScore: Number(row.comment_signal_score || 0),
    negativeCommentSignals: Number(row.negative_comment_signals || 0),
    positiveCommentSignals: Number(row.positive_comment_signals || 0),
    views: Number(row.views || 0),
    comments: Number(row.comments || 0),
    likes: Number(row.likes || 0),
    dislikes: Number(row.dislikes || 0),
  }));
}

function buildSourceReport(rows, nowMs = Date.now()) {
  const normalized = normalizeRows(rows);
  const profile = deals.buildTemperatureProfile(normalized, nowMs);
  const scored = deals.applyTemperatureProfile(normalized, profile);
  const sources = Object.keys(SOURCE_LABELS).map((source) => {
    const sourceRows = scored.filter((item) => item.source === source);
    const temperatures = sourceRows.map((item) => Number(item.temperature || 0));
    const stats = profile.statsBySource.get(source) || { metrics: {} };
    const activeMetrics = deals.TEMPERATURE_METRICS.filter((metric) => stats.metrics?.[metric]?.usable);
    return {
      source,
      label: sourceLabel(source),
      count: sourceRows.length,
      temperatureMean: mean(temperatures),
      temperatureP50: percentile(temperatures, 0.5),
      temperatureP90: percentile(temperatures, 0.9),
      temperatureMax: temperatures.length ? Math.max(...temperatures) : 0,
      activeMetrics,
      metrics: stats.metrics || {},
      qualitySignalsContaminated: Boolean(stats.qualitySignalsContaminated),
      negativeCapRate: Number(stats.negativeCapRate || 0),
    };
  });
  return { normalized, profile, scored, sources };
}

function snapshotTrend(snapshotRows = []) {
  const grouped = new Map();
  for (const row of snapshotRows) {
    if (!grouped.has(row.source)) grouped.set(row.source, []);
    grouped.get(row.source).push(row);
  }
  const trends = new Map();
  for (const [source, rows] of grouped.entries()) {
    rows.sort((a, b) => Date.parse(a.captured_at) - Date.parse(b.captured_at));
    const latest = rows[rows.length - 1];
    const latestMs = Date.parse(latest.captured_at);
    const previous = [...rows].reverse().find((row) => Date.parse(row.captured_at) <= latestMs - 20 * 60 * 60 * 1000);
    trends.set(source, { count: rows.length, latest, previous: previous || null });
  }
  return trends;
}

function metricMean(snapshot, metric) {
  return Number(snapshot?.metrics?.[metric]?.mean || 0);
}

function deltaText(latest, previous, metric) {
  if (!previous) return '수집 시작';
  const before = metricMean(previous, metric);
  const after = metricMean(latest, metric);
  const delta = after - before;
  const sign = delta > 0 ? '+' : '';
  return `${sign}${formatNumber(delta, 1)}`;
}

function buildRecommendations(report) {
  const populated = report.sources.filter((source) => source.count > 0);
  const recommendations = [];
  const means = populated.map((source) => source.temperatureMean);
  const meanGap = means.length ? Math.max(...means) - Math.min(...means) : 0;
  if (meanGap <= 8) {
    recommendations.push(`사이트별 평균 온도 차이가 ${formatNumber(meanGap, 1)}도로 안정 범위(8도 이내)입니다.`);
  } else {
    recommendations.push(`사이트별 평균 온도 차이가 ${formatNumber(meanGap, 1)}도입니다. 상대 점수 비중을 높일지 검토가 필요합니다.`);
  }

  const topRows = [...report.scored].sort((a, b) => b.temperature - a.temperature).slice(0, 20);
  const topCounts = {};
  for (const row of topRows) topCounts[row.source] = (topCounts[row.source] || 0) + 1;
  const topMix = Object.entries(topCounts)
    .sort((a, b) => b[1] - a[1])
    .map(([source, count]) => `${sourceLabel(source)} ${count}건`)
    .join(', ');
  recommendations.push(`상위 20개 구성은 ${topMix || '표본 없음'}입니다.`);

  const saturated = report.scored.filter((item) => item.temperature >= 100).length;
  const saturationRate = report.scored.length ? saturated / report.scored.length : 0;
  if (saturationRate > 0.08) {
    recommendations.push(`100도 비율이 ${formatNumber(saturationRate * 100, 1)}%로 높아 절대 인기 보너스 축소를 검토해야 합니다.`);
  } else {
    recommendations.push(`100도 비율은 ${formatNumber(saturationRate * 100, 1)}%로 과포화되지 않았습니다.`);
  }

  for (const source of populated) {
    if (source.qualitySignalsContaminated) {
      recommendations.push(
        `${source.label}의 부정 상한 비율이 ${formatNumber(source.negativeCapRate * 100, 1)}%라 과거 오염 방어가 활성화되어 있습니다.`,
      );
    }
    if (source.count < 20) {
      recommendations.push(`${source.label} 표본이 ${source.count}건이라 평균·분산 변화는 아직 보수적으로 해석해야 합니다.`);
    }
  }
  return recommendations;
}

function renderMarkdown(rows, snapshotRows = [], now = new Date()) {
  const report = buildSourceReport(rows, now.getTime());
  const trends = snapshotTrend(snapshotRows);
  const recommendations = buildRecommendations(report);
  const config = deals.HOT_SCORE_CONFIG;
  const lines = [
    '# 가지온도 모델 일일 리포트',
    '',
    `- 생성 시각: ${now.toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' })} KST`,
    `- 모델 버전: v${deals.TEMPERATURE_MODEL_VERSION}`,
    `- 표본: 최근 48시간 ${report.scored.length}건`,
    `- 혼합: 사이트 상대 점수 ${formatNumber(config.sourceRelativeWeight * 100)}% + 전체 절대 반응 ${formatNumber(config.globalAbsoluteWeight * 100)}%`,
    '',
    '## 사이트별 온도',
    '',
    '| 사이트 | 표본 | 평균 | 중앙값 | 상위 10% | 최고 | 사용 지표 |',
    '|---|---:|---:|---:|---:|---:|---|',
  ];
  for (const source of report.sources) {
    lines.push(
      `| ${source.label} | ${source.count} | ${formatNumber(source.temperatureMean, 1)}° | ` +
      `${formatNumber(source.temperatureP50, 1)}° | ${formatNumber(source.temperatureP90, 1)}° | ` +
      `${formatNumber(source.temperatureMax, 0)}° | ${source.activeMetrics.join(', ') || '최신성만'} |`,
    );
  }

  lines.push('', '## 반응 분포', '', '| 사이트 | 조회 평균 / p50 / p90 | 댓글 평균 / p50 / p90 | 추천 평균 / p50 / p90 |', '|---|---:|---:|---:|');
  for (const source of report.sources) {
    const metricText = (metric) => {
      const stats = source.metrics[metric] || {};
      return `${formatNumber(stats.rawMean, 1)} / ${formatNumber(stats.p50)} / ${formatNumber(stats.p90)}`;
    };
    lines.push(`| ${source.label} | ${metricText('views')} | ${metricText('comments')} | ${metricText('likes')} |`);
  }

  lines.push('', '## 24시간 추이', '', '| 사이트 | 누적 스냅샷 | 표본 | 조회 평균 변화 | 댓글 평균 변화 | 추천 평균 변화 |', '|---|---:|---:|---:|---:|---:|');
  for (const source of report.sources) {
    const trend = trends.get(source.source);
    lines.push(
      `| ${source.label} | ${trend?.count || 0} | ${trend?.latest?.sample_count || source.count} | ` +
      `${deltaText(trend?.latest, trend?.previous, 'views')} | ` +
      `${deltaText(trend?.latest, trend?.previous, 'comments')} | ` +
      `${deltaText(trend?.latest, trend?.previous, 'likes')} |`,
    );
  }

  lines.push('', '## 자동 점검', '');
  for (const recommendation of recommendations) lines.push(`- ${recommendation}`);
  lines.push('', '이 이슈의 추이를 보면서 상대/절대 비중, 표준편차 범위, 상위 보너스를 함께 조절합니다.', '');
  return lines.join('\n');
}

async function fetchSupabaseRows(endpoint) {
  const url = String(process.env.SUPABASE_URL || '').replace(/\/$/, '');
  const key = String(process.env.SUPABASE_SERVICE_ROLE_KEY || '');
  if (!url || !key) throw new Error('Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY');
  const response = await fetch(`${url}/rest/v1/${endpoint}`, {
    headers: { apikey: key, Authorization: `Bearer ${key}` },
  });
  if (!response.ok) throw new Error(`Supabase request failed (${response.status})`);
  return response.json();
}

async function main() {
  const now = new Date();
  const dealCutoff = encodeURIComponent(new Date(now.getTime() - 48 * 60 * 60 * 1000).toISOString());
  const snapshotCutoff = encodeURIComponent(new Date(now.getTime() - 14 * 24 * 60 * 60 * 1000).toISOString());
  const [rows, snapshots] = await Promise.all([
    fetchSupabaseRows(
      `deals?source=in.(ppomppu,quasar,fmkorea,ruliweb)&deleted_at=is.null&registered_at=gte.${dealCutoff}` +
      '&select=source,registered_at,views,comments,likes,dislikes,comment_signal_score,positive_comment_signals,negative_comment_signals&limit=1000',
    ),
    fetchSupabaseRows(
      `deal_temperature_snapshots?captured_at=gte.${snapshotCutoff}` +
      '&select=source,captured_at,model_version,sample_count,metrics&order=captured_at.asc&limit=5000',
    ).catch(() => []),
  ]);
  process.stdout.write(renderMarkdown(rows, snapshots, now));
}

if (require.main === module) {
  main().catch((error) => {
    process.stderr.write(`${error.message}\n`);
    process.exitCode = 1;
  });
}

module.exports = {
  buildSourceReport,
  snapshotTrend,
  renderMarkdown,
};
