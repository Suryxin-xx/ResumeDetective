export type StatusEvent = { from?: string; to: string; time: string; note?: string };

export type Application = {
  id: number;
  resumeId: number;
  companyName: string;
  positionName: string;
  city: string;
  source: string;
  jobLink: string;
  category: string;
  tags: string;
  jdText: string;
  resumePath: string;
  currentStatus: string;
  stageState: string;
  priority: number;
  statusUpdateTime: string;
  nextAction: string;
  appliedAt: string;
  applicationDeadline: string;
  nextActionDueAt: string;
  lastFollowUpAt: string;
  statusHistory: StatusEvent[];
};

export type Dashboard = {
  total: number;
  active: number;
  interview: number;
  offers: number;
  openTasks: number;
  stageCounts: Record<string, number>;
  demo: boolean;
};

export type JobTarget = {
  id: number;
  companyName: string;
  positionName: string;
  jdText: string;
  jdLink: string;
  city: string;
  status: string;
  notes: string;
  priority: number;
  createdAt: string;
  updatedAt: string;
};

export type Task = {
  id: number;
  title: string;
  dueDate: string;
  priority: number;
  state: "open" | "done";
  notes: string;
  source: string;
};

export type Interview = {
  id: number;
  applicationId: number;
  companyName: string;
  positionName: string;
  round: string;
  interviewTime: string;
  summary: string;
  result: string;
  questions: string;
  weakPoints: string;
  followUp: string;
  createdAt: string;
};

export type Offer = {
  id: number;
  applicationId: number;
  companyName: string;
  positionName: string;
  department: string;
  location: string;
  monthlySalary: number;
  salaryMonths: number;
  bonus: number;
  signingBonus: number;
  otherCompensation: number;
  workIntensity: number;
  growthScore: number;
  interestScore: number;
  locationScore: number;
  stabilityScore: number;
  decisionStatus: string;
  deadline: string;
  notes: string;
  updatedAt: string;
};

export type AIConfig = {
  mode: "direct" | "reasonix";
  baseUrl: string;
  model: string;
  thinking: boolean;
  reasonixPath: string;
  checkReasonixUpdates: boolean;
};

export type AppConfig = {
  port: number;
  workspaceName: string;
  theme: "bright" | "paper" | "dark";
  openBrowserOnStart: boolean;
  startAtLogin: boolean;
  resumeNameTemplate: string;
  autoRenameResumes: boolean;
  checkUpdatesOnStart: boolean;
  updateNetwork: UpdateNetworkConfig;
  autoBackupEnabled: boolean;
  autoBackupHours: number;
  backupRetention: number;
  navigationOrder: string[];
  hiddenNavigation: string[];
  ai: AIConfig;
};

export type SettingsView = { config: AppConfig; apiKeyConfigured: boolean; dataDir: string };
export type UpdateNetworkConfig = { mode: "auto" | "system" | "env" | "custom" | "off"; proxyUrl: string };
export type MigrationStatus = { available: boolean; sourceDir?: string; applications: number; reason: string };
export type SystemInfo = { version: string; dataDir: string; developer: { name: string; email: string; repository: string } };

export type Profile = { id: number; fullName: string; email: string; city: string; education: string; school: string; major: string; targetRole: string; summary: string; githubUrl: string; portfolioUrl: string; updatedAt: string };
export type Material = { id: number; materialType: string; title: string; content: string; tags: string; startTime: string; endTime: string; createdAt: string };
