import {ChatSearch} from '@nlweb-ai/search-components';
import { useState } from 'react';
import SiteDropdown, {type Site} from './components/SiteDropdown'

const SITES = [
  {url: 'yoast-site-recipes.azurewebsites.net', featured: true},
  {url: 'yoast-site-rss.azurewebsites.net', featured: true},
  {url: 'aajtak.in'},
  {url: 'github.com'},
  {url: 'techcrunch.com'},
  {url: '9to5mac.com'},
  {url: 'boingboing.net'},
  {url: 'crackmagazine.net'},
  {url: 'valuewalk.com'},
  {url: 'thewaltdisneycompany.com'},
  {url: 'capgemini.com'},
  {url: 'plesk.com'},
  {url: 'siteminder.com'},
  {url: 'boingo.com'},
  {url: 'adespresso.com'},
  {url: 'loggly.com'},
  {url: 'modpizza.com'},
  {url: 'cpanel.net'},
  {url: 'harvard.edu'},
  {url: 'news.harvard.edu'},
  {url: 'skillcrush.com'},
  {url: 'polk.edu'},
  {url: 'creativecommons.org'},
  {url: 'rollingstones.com'},
  {url: 'katyperry.com'},
  {url: 'usainbolt.com'},
  {url: 'rafaelnadal.com'},
  {url: 'snoopdogg.com'},
  {url: 'riverdance.com'},
  {url: 'news.microsoft.com'},
  {url: 'blog.mozilla.org'},
  {url: 'news.spotify.com'},
  {url: 'nationalarchives.gov.uk'},
  {url: 'blog.cpanel.com'},
  {url: 'news.sap.com'},
  {url: 'finland.fi'},
  {url: 'blogs.cisco.com'},
  {url: 'blog.turbotax.intuit.com'},
  {url: 'blog.alaskaair.com'},
  {url: 'airstream.com'},
  {url: 'wolverineworldwide.com'},
  {url: 'kff.org'},
  {url: 'invisiblechildren.com'},
  {url: 'platformlondon.org'},
  {url: 'travelportland.com'},
  {url: 'tim.blog'},
  {url: 'garyvaynerchuk.com'},
  {url: 'athemes.com'},
  {url: 'generatepress.com'},
  {url: 'wpexplorer.com'},
  {url: 'studiopress.com'},
  {url: 'yoast.com'},
  {url: 'portent.com'},
  {url: 'tri.be'},
  {url: 'hmn.md'},
  {url: 'renweb.com'},
  {url: 'yelpblog.com'},
  {url: 'sprott.carleton.ca'},
  {url: 'pacificrimcollege.online'},
  {url: 'bytes.co'},
  {url: 'talentodigital.madrid.es'},
  {url: 'soapstones.com'},
  {url: 'codefryx.de'},
  {url: 'centremarceau.com'},
  {url: 'riponcathedral.org.uk'},
  {url: 'engineering.fb.com'},
  {url: 'blog.pagely.com'},
  {url: 'daybreaker.com'},
  {url: 'taylorswift.com'},
  {url: 'hodgebank.co.uk'},
  {url: 'newsroom.spotify.com'},
  {url: 'books.disney.com'},
  {url: 'vanyaland.com'},
  {url: 'gizmodo.com'},
  {url: 'kotaku.com'},
  {url: 'jezebel.com'},
  {url: 'theonion.com'},
  {url: 'avclub.com'},
  {url: 'clickhole.com'},
  {url: 'usmagazine.com'},
  {url: 'hongkiat.com'},
  {url: 'speckyboy.com'},
  {url: 'arianagrande.com'},
  {url: 'postmalone.com'},
  {url: 'rihanna.com'},
  {url: 'foofighters.com'},
  {url: 'vice.com'},
  {url: 'pinchofyum.com'},
  {url: 'minimalistbaker.com'},
  {url: 'cookieandkate.com'},
  {url: 'skinnytaste.com'},
  {url: 'budgetbytes.com'},
  {url: 'sallysbakingaddiction.com'},
  {url: 'halfbakedharvest.com'},
  {url: 'theeverygirl.com'},
  {url: 'entrepreneur.com'},
  {url: 'thefashionspot.com'},
  {url: 'outsideonline.com'},
  {url: 'backpacker.com'},
  {url: 'trailrunnermag.com'},
  {url: 'climbing.com'},
  {url: 'cafemom.com'},
  {url: 'greenweddingshoes.com'},
  {url: 'recipetineats.com'},
  {url: 'onceuponachef.com'},
  {url: 'ambitiouskitchen.com'},
];

function App() {
  const [allSites, setAllSites] = useState<Site[]>(SITES);
  const [site, setSite] = useState<Site>(allSites[0]);

  return (
    <div className='p-8'>
      <div className='max-w-3xl mx-auto'>
        <ChatSearch
          endpoint="/ask"
          site={site.url}
        />
        <div className='flex -mt-3 gap-4'>
          <SiteDropdown
            sites={allSites}
            selected={site}
            onSelect={(url) => {
              const targetSite = SITES.find(s => s.url == url);
              if (targetSite) {
                setSite(targetSite)
              } else if (url) {
                setSite({url: url})
                setAllSites(curr => [...curr, {url: url}])
              }
            }}
          />
        </div>
      </div>
    </div>
  )
}

export default App
