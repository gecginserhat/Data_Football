import { getTranslations } from "next-intl/server";

const SECTIONS = ["definitions", "sources", "statsbomb", "imports", "limits"] as const;

/** Tanımlar, veri kaynakları ve lisans atıfları (SPEC §13.1 `/methodology`). */
export default async function Page() {
  const t = await getTranslations("methodology");
  return (
    <>
      <h1 className="mb-6 font-condensed text-2xl font-semibold">{t("title")}</h1>
      <div className="flex max-w-prose flex-col gap-6">
        {SECTIONS.map((key) => (
          <section key={key} aria-labelledby={`m-${key}`}>
            <h2 id={`m-${key}`} className="mb-2 font-condensed text-lg font-semibold">
              {t(`${key}.title`)}
            </h2>
            <p className="text-sm leading-6 text-ink-2">{t(`${key}.body`)}</p>
            {key === "statsbomb" ? (
              <p className="mt-2 text-sm">
                <a
                  href="https://github.com/statsbomb/open-data"
                  className="text-pri underline underline-offset-2"
                  rel="noreferrer"
                >
                  {t("statsbomb.link")}
                </a>
              </p>
            ) : null}
          </section>
        ))}
      </div>
    </>
  );
}
