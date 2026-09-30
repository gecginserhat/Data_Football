import { render, screen } from "@testing-library/react";
import { EmptyState, SampleSizeBadge, TeamBadge, isLowSample } from "./index";

describe("EmptyState", () => {
  it("tells the user what to do", () => {
    render(<EmptyState title="Henüz rutin yok" description="Şablondan bir rutin oluşturun." />);
    expect(screen.getByRole("heading", { name: "Henüz rutin yok" })).toBeInTheDocument();
    expect(screen.getByText("Şablondan bir rutin oluşturun.")).toBeInTheDocument();
  });
});

describe("SampleSizeBadge", () => {
  it("flags fewer than 8 attempts or 5 matches", () => {
    expect(isLowSample(7)).toBe(true);
    expect(isLowSample(8)).toBe(false);
    expect(isLowSample(undefined, 4)).toBe(true);
    expect(isLowSample(20, 5)).toBe(false);
  });

  it("renders nothing when the sample is large enough", () => {
    const { container } = render(<SampleSizeBadge n={12} matches={6} label="Az veri" />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders the label for small samples", () => {
    render(<SampleSizeBadge n={3} label="Az veri" />);
    expect(screen.getByText("Az veri")).toBeInTheDocument();
  });
});

describe("TeamBadge", () => {
  it("shows the short code with the full name as title", () => {
    render(<TeamBadge code="TS" name="Trabzonspor" />);
    expect(screen.getByTitle("Trabzonspor")).toHaveTextContent("TS");
  });
});
