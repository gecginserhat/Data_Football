import { formatDuration, formatSize, isBusy } from "./report-display";

describe("report display", () => {
  it("formats durations in Turkish", () => {
    expect(formatDuration(1840)).toBe("1,8 sn");
    expect(formatDuration(65_000)).toBe("1 dk 05 sn");
    expect(formatDuration(null)).toBeNull();
    expect(formatDuration(1840, "en")).toBe("1.8 s");
  });

  it("formats sizes", () => {
    expect(formatSize(245_760)).toBe("240 KB");
    expect(formatSize(1_572_864)).toBe("1,5 MB");
    expect(formatSize(100)).toBe("1 KB");
  });

  it("knows which statuses are still running", () => {
    expect(isBusy("queued")).toBe(true);
    expect(isBusy("running")).toBe(true);
    expect(isBusy("ready")).toBe(false);
    expect(isBusy("failed")).toBe(false);
  });
});
