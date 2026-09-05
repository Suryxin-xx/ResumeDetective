export const stageStateOptions = [
  { value: "待处理", label: "待我处理" },
  { value: "已安排", label: "已安排时间" },
  { value: "已完成，等待结果", label: "等待公司结果" },
] as const;

const stageStateLabels: Record<string, string> = {
  "待处理": "待我处理",
  "已安排": "已安排时间",
  "已完成，等待结果": "等待公司结果",
  "已完成": "本环节已结束",
};

export function stageStateLabel(value: string) {
  return stageStateLabels[value] || value || "未设置";
}

export function stageStateChoices(current: string) {
  const choices = [...stageStateOptions];
  if (current && !choices.some((choice) => choice.value === current)) {
    return [{ value: current, label: stageStateLabel(current) }, ...choices];
  }
  return choices;
}
