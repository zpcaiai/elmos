"""Sandbox inventory/recovery in the existing deployment journal, not a dispatch ledger."""
import re
from .contracts import digest, require


class NativeCleanupJournal:
    def __init__(self, journal, scope, request_digest, authority):
        self.journal,self.scope,self.request_digest,self.authority=journal,scope,request_digest,authority

    @property
    def labels(self):
        return {'io.elmos.scope-digest':digest(self.scope.key), 'io.elmos.request-digest':self.request_digest}

    def prepare(self, name, image):
        require(re.fullmatch(r'elmos-deployment-[0-9a-f]{32}',name), 'cleanup_container_name')
        self.journal.put(self.scope,'native-sandbox',name,{'name':name,'image':image,
            'request_digest':self.request_digest,'labels':self.labels})

    def cleaned(self, name):
        record=self.journal.get(self.scope,'native-sandbox',name)
        require(record['request_digest'] == self.request_digest, 'cleanup_request_binding')
        self.journal.put(self.scope,'native-sandbox-cleaned',name,{'sandbox_digest':digest(record)})

    def pending(self, limit=100):
        require(type(limit) is int and 1 <= limit <= 100, 'cleanup_query_bounds')
        with self.journal.connection() as connection:
            rows=connection.execute('''SELECT b.id FROM objects b
                LEFT JOIN objects c ON c.scope=b.scope AND c.kind='native-sandbox-cleaned' AND c.id=b.id
                WHERE b.scope=? AND b.kind='native-sandbox' AND c.id IS NULL
                AND json_extract(CAST(b.body AS TEXT),'$.request_digest')=? ORDER BY b.id LIMIT ?''',
                (self.scope.key,self.request_digest,limit)).fetchall()
        return [row['id'] for row in rows]

    def reconcile(self, process, name):
        record=self.journal.get(self.scope,'native-sandbox',name)
        require(record['request_digest'] == self.request_digest and record['labels'] == self.labels
                and record['image'] == process.image, 'cleanup_request_binding')
        # This host operation must fence the original worker/daemon dispatch and
        # authorize cleanup. Expiry alone does not prove the old worker is dead.
        self.authority.require_fenced_cleanup(self.scope,record)
        entries=process._json(['container','ls','--all','--no-trunc','--filter','name=^/'+name+'$',
                               '--format','{{json .}}'])
        # Dedicated exact-name query uses one JSON object or an empty list via
        # the implementation below; no unscoped sweep is permitted.
        if entries == []:
            self.cleaned(name)
            return 'ABSENT_AFTER_FENCE'
        require(type(entries) is dict and entries.get('Names') == name, 'cleanup_inventory_binding')
        container=process._json(['container','inspect',name])[0]
        require(container.get('Config',{}).get('Image') == record['image']
                and all(container.get('Config',{}).get('Labels',{}).get(k) == v for k,v in self.labels.items()),
                'cleanup_container_binding')
        result=process.client.run(['container','rm','--force',name],30)
        require(result.code == 0, 'cleanup_requires_reconciliation')
        self.cleaned(name)
        return 'REMOVED_AFTER_FENCE'
