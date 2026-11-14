export default function About({ active }) {
  return (
    <section className="about" hidden={!active}>
      <h2 className="section-title">About</h2>
      <div className="divider" aria-hidden="true"><span /></div>

      <div className="about-body">
        <p>
          ASAP Chem Hub brings the newest chemistry in one place: articles published ahead of print in
          37 journals, shown with their graphical abstracts, and new international (WO) patent applications.
          Both are sorted by research topic, so you can follow degraders, catalysis or OLED materials without
          visiting a dozen sites.
        </p>

        <h3>Where the data comes from</h3>
        <ul>
          <li>Articles: publisher RSS feeds (ACS, Wiley, AAAS, Springer Nature), Crossref (RSC and ChemRxiv) and the Springer Nature APIs.</li>
          <li>Patents: the European Patent Office's Open Patent Services.</li>
          <li>Figures are shown from each publisher's own server, never copied, and every card links to the original.</li>
        </ul>

        <h3>How topics are chosen</h3>
        <p>
          Topics are assigned by keyword rules on the title and abstract. Antibody-drug conjugates, antibodies
          and OLED materials on the patent side come from patent classification codes. Tagging is automatic, so
          an item can be missed or mislabelled; the search box finds anything by its words.
        </p>

        <h3>Limits</h3>
        <p>
          The patent section is for awareness only. It is not a freedom-to-operate or patentability search.
          Articles are kept for 30 days and patents for 90. Figures are shown only from the publishers' own servers
          and are never stored or redistributed by this site; titles and abstracts come from the publishers'
          public feeds, and every item links to the original.
        </p>

        <h3>Who made it</h3>
        <p>
          Designed and built by Vijayarajan Devannah, a PhD synthetic organic chemist working in medicinal and
          OLED chemistry and in data engineering.
        </p>

        <p className="image-credit">Banner image: AI-generated for ASAP Chem Hub.</p>
      </div>
    </section>
  );
}
