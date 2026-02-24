export type SpeakerRole = "interviewer" | "interviewee";

export type InterviewMessage = {
  role: SpeakerRole;
  content: string;
  at: string;
};
