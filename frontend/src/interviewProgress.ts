import type { Interview } from "./types";

export const interviewResultLabel = (result: string) => result === "待确认" ? "结果待通知" : result || "结果待通知";

export function interviewStage(round: string) {
  if (round === "AI 面试") return "AI 面试";
  if (round === "HR 面") return "HR 面";
  return "业务面试";
}

export function interviewStageState(result: string) {
  if (result === "待面试") return "已安排";
  if (result === "待确认") return "已完成，等待结果";
  return "已完成";
}

export function interviewProgressLabel(interview?: Interview) {
  if (!interview) return "";
  return `${interview.round} · ${interviewResultLabel(interview.result)}`;
}

export function preferredInterview(records: Interview[]) {
  const now = Date.now();
  const upcoming = records
    .filter((item) => item.result !== "未通过")
    .filter((item) => item.interviewTime && new Date(item.interviewTime).getTime() >= now)
    .sort((a, b) => new Date(a.interviewTime).getTime() - new Date(b.interviewTime).getTime());
  if (upcoming.length) return upcoming[0];
  return [...records].sort((a, b) => interviewTimestamp(b) - interviewTimestamp(a))[0];
}

export function interviewTimestamp(interview: Interview) {
  const timestamp = new Date(interview.interviewTime || interview.createdAt).getTime();
  return Number.isFinite(timestamp) ? timestamp : 0;
}
