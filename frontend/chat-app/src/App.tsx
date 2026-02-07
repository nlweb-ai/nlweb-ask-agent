import {
  ChatSearch,
  useNlWeb,
  DebugTool,
  SiteDropdown,
  useSearchSession,
  useSearchSessions,
  HistorySidebar,
  type SearchSession,
} from "@nlweb-ai/search-components";
import { useState } from "react";

const SITES = [
  { url: "yoast-site-recipes.azurewebsites.net", featured: true },
  { url: "yoast-site-rss.azurewebsites.net", featured: true },
  { url: "aajtak.in" },
  { url: "techcrunch.com" },
  { url: "9to5mac.com" },
  { url: "boingboing.net" },
  { url: "crackmagazine.net" },
  { url: "valuewalk.com" },
  { url: "thewaltdisneycompany.com" },
  { url: "capgemini.com" },
  { url: "plesk.com" },
  { url: "siteminder.com" },
  { url: "boingo.com" },
  { url: "adespresso.com" },
  { url: "loggly.com" },
  { url: "modpizza.com" },
  { url: "cpanel.net" },
  { url: "harvard.edu" },
  { url: "news.harvard.edu" },
  { url: "skillcrush.com" },
  { url: "polk.edu" },
  { url: "creativecommons.org" },
  { url: "rollingstones.com" },
  { url: "katyperry.com" },
  { url: "usainbolt.com" },
  { url: "rafaelnadal.com" },
  { url: "snoopdogg.com" },
  { url: "riverdance.com" },
  { url: "news.microsoft.com" },
  { url: "blog.mozilla.org" },
  { url: "news.spotify.com" },
  { url: "nationalarchives.gov.uk" },
  { url: "blog.cpanel.com" },
  { url: "news.sap.com" },
  { url: "finland.fi" },
  { url: "blogs.cisco.com" },
  { url: "blog.turbotax.intuit.com" },
  { url: "blog.alaskaair.com" },
  { url: "airstream.com" },
  { url: "wolverineworldwide.com" },
  { url: "kff.org" },
  { url: "invisiblechildren.com" },
  { url: "platformlondon.org" },
  { url: "travelportland.com" },
  { url: "tim.blog" },
  { url: "garyvaynerchuk.com" },
  { url: "athemes.com" },
  { url: "generatepress.com" },
  { url: "wpexplorer.com" },
  { url: "studiopress.com" },
  { url: "yoast.com" },
  { url: "portent.com" },
  { url: "tri.be" },
  { url: "hmn.md" },
  { url: "renweb.com" },
  { url: "yelpblog.com" },
  { url: "sprott.carleton.ca" },
  { url: "pacificrimcollege.online" },
  { url: "bytes.co" },
  { url: "talentodigital.madrid.es" },
  { url: "soapstones.com" },
  { url: "codefryx.de" },
  { url: "centremarceau.com" },
  { url: "riponcathedral.org.uk" },
  { url: "engineering.fb.com" },
  { url: "blog.pagely.com" },
  { url: "daybreaker.com" },
  { url: "taylorswift.com" },
  { url: "hodgebank.co.uk" },
  { url: "newsroom.spotify.com" },
  { url: "books.disney.com" },
  { url: "vanyaland.com" },
  { url: "gizmodo.com" },
  { url: "kotaku.com" },
  { url: "jezebel.com" },
  { url: "theonion.com" },
  { url: "avclub.com" },
  { url: "clickhole.com" },
  { url: "usmagazine.com" },
  { url: "hongkiat.com" },
  { url: "speckyboy.com" },
  { url: "arianagrande.com" },
  { url: "postmalone.com" },
  { url: "rihanna.com" },
  { url: "foofighters.com" },
  { url: "vice.com" },
  { url: "pinchofyum.com" },
  { url: "minimalistbaker.com" },
  { url: "cookieandkate.com" },
  { url: "skinnytaste.com" },
  { url: "budgetbytes.com" },
  { url: "sallysbakingaddiction.com" },
  { url: "halfbakedharvest.com" },
  { url: "theeverygirl.com" },
  { url: "entrepreneur.com" },
  { url: "thefashionspot.com" },
  { url: "outsideonline.com" },
  { url: "backpacker.com" },
  { url: "trailrunnermag.com" },
  { url: "climbing.com" },
  { url: "cafemom.com" },
  { url: "greenweddingshoes.com" },
  { url: "recipetineats.com" },
  { url: "onceuponachef.com" },
  { url: "ambitiouskitchen.com" },
];

function App() {
  const [site, setSite] = useState(SITES[0]);
  // Append URL query parameters to the endpoint for config overrides
  const queryString = window.location.search;
  const endpoint = `/ask${queryString}`;
  const config = {
    endpoint: endpoint,
    site: site.url,
    maxResults: 9,
    numRetrievalResults: 50,
  };
  const nlweb = useNlWeb(config);
  const localSessions = useSearchSessions();
  const [sessionId, setSessionId] = useState<string>(crypto.randomUUID());
  const { searches, addSearch, addResults } = useSearchSession(sessionId);
  async function startSearch(query: string) {
    nlweb.clearResults();
    const newId = localSessions.sessions.some((s) => s.sessionId === sessionId)
      ? crypto.randomUUID()
      : sessionId;
    await localSessions.startSession(newId, query, {
      site: site.url,
      endpoint: endpoint,
    });
    setSessionId(newId);
    return newId;
  }
  function endSearch() {
    setSessionId(crypto.randomUUID());
    nlweb.clearResults();
    nlweb.cancelSearch();
  }
  function selectSession(session: SearchSession) {
    nlweb.clearResults();
    nlweb.cancelSearch();
    setSessionId(session.sessionId);
    setSite(
      SITES.find((s) => s.url == session.backend.site) || {
        url: session.backend.site,
      },
    );
  }
  return (
    <div className="h-screen flex items-stretch">
      <HistorySidebar
        sessions={localSessions.sessions}
        onSelect={selectSession}
        onDelete={localSessions.deleteSession}
        onCreate={endSearch}
      />
      <div className="p-8 flex-1">
        <div className="max-w-3xl mx-auto">
          <ChatSearch
            sessionId={sessionId}
            startSession={startSearch}
            endSession={endSearch}
            searches={searches}
            addSearch={addSearch}
            addResults={addResults}
            nlweb={nlweb}
            config={config}
            sidebar={
              <HistorySidebar
                sessions={localSessions.sessions}
                onSelect={selectSession}
                onDelete={localSessions.deleteSession}
                onCreate={endSearch}
              />
            }
          >
            <div className="absolute z-50 top-2 right-16">
              <DebugTool
                streamingState={nlweb}
                searches={searches}
                config={config}
              />
            </div>
          </ChatSearch>
          <SiteDropdown
            sites={SITES}
            selected={site}
            onSelect={(url) =>
              setSite(
                SITES.find((s) => s.url == url) || {
                  url: url || "",
                },
              )
            }
          />
        </div>
      </div>
    </div>
  );
}

export default App;
