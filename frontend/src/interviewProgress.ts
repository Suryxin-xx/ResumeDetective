import type { Application, Interview } from "./types";

export const interviewResultLabel = (result: string) => result === "待确认" ? "结果待通知" : result || "结果待通知";

export function interviewStage(round: string) {
  if (round === "AI 面试") return "AI 面试";
  if (round === "HR 面") return "HR 面";
  return "业务面试";
}

export function nextInterviewRound(round: string) {
  if (round === "AI 面试") return "一面";
  if (round === "一面") return "二面";
  if (round === "二面") return "三面";
  return "";
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
  // A newly created, undated next round must outrank a completed earlier round.
  return [...records].sort((a, b) => roundRank(b.round) - roundRank(a.round) ||
    interviewTimestamp(b) - interviewTimestamp(a) || b.id - a.id)[0];
}

function roundRank(round: string) {
  return ({ "AI 面试": 0, "一面": 1, "二面": 2, "三面": 3, "HR 面": 4 } as Record<string, number>)[round] ?? 1;
}

export type InterviewProgress = { interview?: Interview; kind: "scheduled" | "unscheduled" | "next-round" | "waiting" | "history"; nextRound: string };

export function applicationInterviewProgress(application: Application, records: Interview[]): InterviewProgress {
  const currentStage = ["业务面试", "HR 面", "AI 面试"].includes(application.currentStatus);
  const relevant = currentStage ? records.filter(record => interviewStage(record.round) === application.currentStatus) : records;
  const interview = preferredInterview(relevant);
  if (!currentStage) return { interview, kind: "history", nextRound: "" };
  // Asynchronous AI assessments need no interview record; retain manual progress.
  if (!interview && application.currentStatus === "AI 面试") return { kind: "history", nextRound: "" };
  if (!interview) return { kind: "unscheduled", nextRound: application.currentStatus === "HR 面" ? "HR 面" : application.currentStatus === "AI 面试" ? "AI 面试" : "一面" };
  if (interview.result === "待面试") return { interview, kind: interview.interviewTime ? "scheduled" : "unscheduled", nextRound: "" };
  if (interview.result === "待确认") return { interview, kind: "waiting", nextRound: "" };
  if (interview.result === "通过") return { interview, kind: "next-round", nextRound: nextInterviewRound(interview.round) };
  return { interview, kind: "history", nextRound: "" };
}

export function applicationInterviewStateLabel(application: Application, records: Interview[]) {
  const progress = applicationInterviewProgress(application, records);
  if (progress.kind === "next-round") return "本轮通过，等待后续通知";
  if (progress.kind === "waiting") return "等待面试结果";
  if (progress.kind === "scheduled") return "已安排面试";
  if (progress.kind === "unscheduled") return "面试安排待补充";
  return "";
}

export function effectiveStageState(application: Application, records: Interview[]) {
  const { kind } = applicationInterviewProgress(application, records);
  if (kind === "scheduled") return "已安排";
  if (kind === "unscheduled") return "待处理";
  if (kind === "waiting" || kind === "next-round") return "已完成，等待结果";
  return application.stageState;
}

export function interviewTimestamp(interview: Interview) {
  const timestamp = new Date(interview.interviewTime || interview.createdAt).getTime();
  return Number.isFinite(timestamp) ? timestamp : 0;
}
