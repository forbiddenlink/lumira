const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(process.argv[2] || path.resolve(__dirname, '../../static/js/matrix-preview.js'), 'utf8');
function setup(fetchResponse) {
  class Element {
    constructor(){this.listeners={};this.children=[];this.textContent='';this.value='';this.disabled=false;}
    addEventListener(event, fn){this.listeners[event]=fn;}
    append(...items){this.children.push(...items);}
    replaceChildren(){this.children=[];}
    dispatchEvent(event){return this.listeners[event.type]?.(event);}
    focus(){this.focused=true;}
  }
  const ids=Object.fromEntries(['request-prompt','matrix-preview-button','matrix-preview-status','matrix-preview-results'].map(id=>[id,new Element()]));
  const calls=[];
  vm.runInNewContext(source,{document:{getElementById:id=>ids[id],createElement:()=>new Element()},Event:class {constructor(type){this.type=type;}},Error,fetch:async(url,options)=>{calls.push({url,options});return fetchResponse();}});
  return {ids,calls,click:()=>ids['matrix-preview-button'].listeners.click()};
}
const response=(body,ok=true)=>({ok,json:async()=>body});
(async()=>{
 let passed=0;
 const app=setup(()=>response({combinations:['red cat','blue cat'],total_combinations:'4'}));
 await app.click();assert.equal(app.calls.length,0);assert.equal(app.ids['request-prompt'].focused,true);passed++;
 app.ids['request-prompt'].value='a {red|blue} cat';await app.click();
 assert.equal(app.calls.length,1);assert.equal(app.calls[0].url,'/api/prompt/matrix/preview');assert.equal(JSON.parse(app.calls[0].options.body).limit,6);assert.match(app.ids['matrix-preview-status'].textContent,/Showing 2 of 4/);passed++;
 const use=app.ids['matrix-preview-results'].children[1].children[1];use.listeners.click();
 assert.equal(app.ids['request-prompt'].value,'blue cat');assert.equal(app.ids['matrix-preview-results'].children.length,0);assert.equal(app.calls.length,1);assert.match(app.ids['matrix-preview-status'].textContent,/Nothing has been generated or submitted/);passed++;
 const failed=setup(()=>response({detail:'Invalid syntax: Empty option'},false));failed.ids['request-prompt'].value='{}';await failed.click();assert.match(failed.ids['matrix-preview-status'].textContent,/Invalid syntax/);assert.equal(failed.ids['matrix-preview-button'].disabled,false);passed++;
 const malicious=setup(()=>response({combinations:['<img src=x onerror=alert(1)>'],total_combinations:'1'}));malicious.ids['request-prompt'].value='hello';await malicious.click();assert.equal(malicious.ids['matrix-preview-results'].children[0].children[0].textContent,'<img src=x onerror=alert(1)>');passed++;
 let release;const stale=setup(()=>new Promise(resolve=>{release=resolve;}));stale.ids['request-prompt'].value='old';const pending=stale.click();stale.ids['request-prompt'].value='new';stale.ids['request-prompt'].dispatchEvent({type:'input'});release(response({combinations:['old'],total_combinations:'1'}));await pending;assert.equal(stale.ids['matrix-preview-results'].children.length,0);assert.equal(stale.ids['matrix-preview-status'].textContent,'');passed++;
 const invalid=setup(()=>response({combinations:['text'],total_combinations:1}));invalid.ids['request-prompt'].value='text';await invalid.click();assert.match(invalid.ids['matrix-preview-status'].textContent,/Preview unavailable/);passed++;
 const network=setup(()=>{throw Error('Offline');});network.ids['request-prompt'].value='text';await network.click();assert.equal(network.ids['matrix-preview-button'].disabled,false);assert.match(network.ids['matrix-preview-status'].textContent,/Offline/);passed++;
 console.log(JSON.stringify({passed,realNetworkCalls:0,generationCalls:0}));
})().catch(error=>{console.error(error);process.exitCode=1;});
