import { ATLANTIC_TIME_ZONE } from './config.js';

const atlanticParts = new Intl.DateTimeFormat('en-US', {
  timeZone: ATLANTIC_TIME_ZONE,
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
  month: 'short',
  day: 'numeric',
  timeZoneName: 'short',
});

function partOf(parts, type) {
  const found = parts.find((entry) => entry.type === type);
  return found === undefined ? '' : found.value;
}

function pad2(value) {
  return String(value).padStart(2, '0');
}

export function remainingText(remainingMs) {
  const total = Math.max(0, Math.floor(remainingMs / 1000));
  const days = Math.floor(total / 86400);
  const hours = Math.floor((total % 86400) / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  const clock = `${pad2(hours)}:${pad2(minutes)}:${pad2(seconds)}`;
  return days > 0 ? `${days}d ${clock}` : clock;
}

export function formatUtc(instant) {
  const date = new Date(instant);
  if (Number.isNaN(date.getTime())) {
    return String(instant);
  }
  return `${date.toISOString().slice(0, 10)} ${date.toISOString().slice(11, 19)}Z`;
}

export function formatUtcShort(instant) {
  const date = new Date(instant);
  if (Number.isNaN(date.getTime())) {
    return String(instant);
  }
  return `${date.toISOString().slice(0, 10)} ${date.toISOString().slice(11, 16)}Z`;
}

export function formatAtlantic(instant) {
  const date = new Date(instant);
  if (Number.isNaN(date.getTime())) {
    return String(instant);
  }
  const parts = atlanticParts.formatToParts(date);
  return `${partOf(parts, 'hour')}:${partOf(parts, 'minute')} ${partOf(
    parts,
    'timeZoneName',
  )}, ${partOf(parts, 'month')} ${partOf(parts, 'day')}`;
}

export function seconds(value) {
  return `${value.toFixed(1)} s`;
}

export function degrees(value) {
  return value.toFixed(1);
}

export function percent(value) {
  return `${(value * 100).toFixed(1)}%`;
}

export function isoDate(date) {
  return date.toISOString().slice(0, 10);
}

export function addDays(date, days) {
  return new Date(date.getTime() + days * 86400000);
}
