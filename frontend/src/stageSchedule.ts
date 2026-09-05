import type { Application } from "./types";

export type StageTimeFilter = "全部时间" | "已逾期" | "今天" | "未来3天" | "未来7天" | "暂无安排";

export function stageTimeValue(item: Pick<Application, "stageScheduledAt" | "stageTimeType">): number {
  const value = item.stageScheduledAt?.trim();
  if (!value) return Number.POSITIVE_INFINITY;
  const dateOnly = /^\d{4}-\d{2}-\d{2}$/.test(value);
  const normalized = dateOnly
    ? `${value}T${item.stageTimeType === "deadline" ? "23:59:59" : "00:00:00"}`
    : value;
  const timestamp = new Date(normalized).getTime();
  return Number.isFinite(timestamp) ? timestamp : Number.POSITIVE_INFINITY;
}

export function stageTimeLabel(item: Pick<Application, "stageScheduledAt" | "stageTimeType">): string {
  const value = item.stageScheduledAt?.trim();
  if (!value) return "";
  const dateOnly = /^\d{4}-\d{2}-\d{2}$/.test(value);
  const timestamp = stageTimeValue(item);
  if (!Number.isFinite(timestamp)) return value.replace("T", " ");
  const date = new Date(timestamp);
  const day = new Intl.DateTimeFormat("zh-CN", { month: "numeric", day: "numeric" }).format(date);
  if (dateOnly) return item.stageTimeType === "deadline" ? `${day}前完成` : `${day}参加`;
  const time = new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false }).format(date);
  return item.stageTimeType === "deadline" ? `${day} ${time} 前完成` : `${day} ${time} 开始`;
}

export function completedTimeLabel(value: string): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return `${value.replace("T", " ").slice(0, 16)} 已完成`;
  return `${new Intl.DateTimeFormat("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false }).format(date)} 已完成`;
}

export function stageTimeTone(item: Pick<Application, "stageScheduledAt" | "stageCompletedAt" | "stageTimeType">): "none" | "done" | "overdue" | "urgent" | "soon" | "future" {
  if (item.stageCompletedAt) return "done";
  const time = stageTimeValue(item);
  if (!Number.isFinite(time)) return "none";
  const remaining = time - Date.now();
  if (remaining < 0) return "overdue";
  if (remaining <= 86_400_000) return "urgent";
  if (remaining <= 3 * 86_400_000) return "soon";
  return "future";
}

export function stageTimeRelative(item: Pick<Application, "stageScheduledAt" | "stageCompletedAt" | "stageTimeType">): string {
  if (item.stageCompletedAt) return completedTimeLabel(item.stageCompletedAt);
  const time = stageTimeValue(item);
  if (!Number.isFinite(time)) return "";
  const remaining = time - Date.now();
  if (remaining >= 0) return stageTimeLabel(item);
  const days = Math.max(1, Math.ceil(Math.abs(remaining) / 86_400_000));
  return `已逾期 ${days} 天`;
}

export function matchesStageTimeFilter(item: Application, filter: StageTimeFilter): boolean {
  if (filter === "全部时间") return true;
  const time = stageTimeValue(item);
  if (filter === "暂无安排") return !Number.isFinite(time);
  if (!Number.isFinite(time) || item.stageCompletedAt) return false;
  const now = new Date();
  const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const endToday = startToday + 86_400_000;
  if (filter === "已逾期") return time < Date.now();
  if (filter === "今天") return time >= startToday && time < endToday;
  const horizon = filter === "未来3天" ? 3 : 7;
  return time >= Date.now() && time <= Date.now() + horizon * 86_400_000;
}
