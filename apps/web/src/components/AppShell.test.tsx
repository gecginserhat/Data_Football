import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import messages from "../../messages/tr.json";
import { AppShell } from "./AppShell";

vi.mock("next/navigation", () => ({ usePathname: () => "/prep/123" }));

function renderShell() {
  return render(
    <NextIntlClientProvider locale="tr" messages={messages}>
      <AppShell
        visible={["overview", "prep", "league", "me"]}
        clubName="Trabzonspor"
        userName="Analist"
        footer={null}
      >
        <p>içerik</p>
      </AppShell>
    </NextIntlClientProvider>,
  );
}

describe("AppShell", () => {
  it("renders only the visible routes in the main navigation", () => {
    renderShell();
    const nav = screen.getByRole("navigation", { name: "Ana menü" });
    const links = Array.from(nav.querySelectorAll("a")).map((a) => a.textContent);
    expect(links).toEqual(["Genel bakış", "Maç hazırlığı", "Lig", "Profilim"]);
  });

  it("marks the current section as the active page", () => {
    renderShell();
    const nav = screen.getByRole("navigation", { name: "Ana menü" });
    const active = nav.querySelector('[aria-current="page"]');
    expect(active).toHaveTextContent("Maç hazırlığı");
  });

  it("shows the club name", () => {
    renderShell();
    expect(screen.getAllByText("Trabzonspor").length).toBeGreaterThan(0);
  });
});
