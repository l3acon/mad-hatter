/* Execute the generated ServiceNow rules against a small GlideRecord test double. */
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const scripts = JSON.parse(fs.readFileSync(0, 'utf8'));
const CR = 'a'.repeat(32), RITM = 'b'.repeat(32), GROUP = 'c'.repeat(32);
let tables, launches, response, context, nextId;
const snapshot = {server_build_os: 'rhel', ocpv_vm_name: 'test-server', ocpv_instancetype_name: 'u1.xlarge'};
function record(table, initial = {}, old = initial) {
    const target = {_table: table, _data: structuredClone(initial), _old: structuredClone(old), _queries: [], _rows: [], _aborted: false};
    const methods = {
        get(id) {
            const data = (tables[table] || []).find(row => row.sys_id === id);
            if (!data) return false;
            target._data = structuredClone(data); target._old = structuredClone(data); return true;
        },
        getUniqueValue() { return target._data.sys_id; },
        addQuery(key, val) { target._queries.push([key, String(val)]); },
        query() { target._rows = (tables[table] || []).filter(row => target._queries.every(([k, v]) => String(row[k]) === v)).map(row => structuredClone(row)); },
        next() { if (!target._rows.length) return false; target._data = target._rows.shift(); return true; },
        initialize() { target._data = {}; },
        insert() {
            target._data.sys_id = (nextId++).toString(16).padStart(32, '0');
            target._data.number = 'CHG0001';
            target._data.u_aap_workflow_job_id = '';
            (tables[table] ||= []).push(structuredClone(target._data));
            return target._data.sys_id;
        },
        update() {
            const index = (tables[table] || []).findIndex(row => row.sys_id === target._data.sys_id);
            assert.ok(index >= 0, 'update requires persisted record');
            tables[table][index] = structuredClone(target._data);
            return target._data.sys_id;
        },
        setAbortAction(value) { target._aborted = value; },
    };
    return new Proxy(target, {
        get(obj, key) {
            if (key in methods) return methods[key];
            if (key in obj) return obj[key];
            if (target._data[key] && typeof target._data[key] === 'object') return target._data[key];
            return {
                toString: () => String(target._data[key] ?? ''),
                valueOf: () => target._data[key] ?? '',
                changes: () => String(target._data[key] ?? '') !== String(target._old[key] ?? ''),
                changesTo: val => String(target._data[key] ?? '') === String(val) && String(target._old[key] ?? '') !== String(val),
            };
        },
        set(obj, key, value) {
            if (key.startsWith('_')) obj[key] = value;
            else obj._data[key] = value && typeof value === 'object' && 'toString' in value ? value.toString() : value;
            return true;
        },
    });
}
function reset(overrides = {}) {
    const cr = {sys_id: CR, number: 'CHG001', u_aap_integration: 'server-build',
        parent: RITM, correlation_id: RITM, correlation_display: 'server-build',
        u_aap_build_parameters: JSON.stringify(snapshot), u_aap_launch_status: 'pending',
        u_aap_workflow_job_id: '', approval: 'requested', state: '-4', ...overrides};
    tables = {change_request: [cr], sc_req_item: [{sys_id: RITM, number: 'RITM001', state: '1', cat_item: {name: 'server-build'}}],
        sys_user_group: [{sys_id: GROUP, active: 'true'}],
        sc_item_option_mtom: Object.entries(snapshot).map(([name, value]) => ({request_item: RITM, sc_item_option: {item_option_new: {name}, value}}))};
    launches = []; response = {status: 201, body: '{"id": 123}'}; nextId = 1;
    context = vm.createContext({
        GlideRecord: function(table) { return record(table); },
        GlideDateTime: function() { this.addSeconds = () => {}; this.toString = () => '2026-10-20 12:00:00'; },
        AAPIntegration: function() {
            this.launchWorkflow = (id, vars) => { launches.push({id, vars}); if (response instanceof Error) throw response; return response; };
            this.launchJobTemplate = (id, vars) => { launches.push({id, vars, type: 'job'}); return response; };
        },
        gs: {error() {}, addErrorMessage() {}},
    });
}
function runApproval(changes = {}) {
    const old = structuredClone(tables.change_request[0]);
    const current = record('change_request', {...old, ...changes}, old);
    context.current = current; context.previous = record('change_request', old);
    vm.runInContext(scripts.claim, context);
    if (!current._aborted) {
        current.update();
        vm.runInContext(scripts.approval, context);
    }
    return current;
}
let tests = 0;
function test(name, fn) { reset(); fn(); tests++; }
test('no provisioning during catalog order; one normal change with allowlisted snapshot', () => {
    tables.change_request = [];
    context.current = record('sc_req_item', tables.sc_req_item[0]); context.previous = null;
    vm.runInContext(scripts.catalog, context);
    assert.equal(launches.length, 0);
    assert.equal(tables.change_request.length, 1);
    const cr = tables.change_request[0];
    assert.equal(cr.type, 'normal'); assert.equal(cr.state, '-4'); assert.equal(cr.parent, RITM);
    assert.deepEqual(JSON.parse(cr.u_aap_build_parameters), snapshot);
    vm.runInContext(scripts.catalog, context);
    assert.equal(tables.change_request.length, 1);
});
test('invalid VM input creates no CR', () => {
    tables.change_request = [];
    tables.sc_item_option_mtom[1].sc_item_option.value = '../bad';
    context.current = record('sc_req_item', tables.sc_req_item[0]); context.previous = null;
    vm.runInContext(scripts.catalog, context);
    assert.equal(tables.change_request.length, 0); assert.equal(tables.sc_req_item[0].state, '4');
});
test('intermediate approval does not launch', () => {
    runApproval({approval: 'approved'}); assert.equal(launches.length, 0);
});
test('Scheduled without approval does not launch', () => {
    runApproval({state: '-2'}); assert.equal(launches.length, 0);
});
test('approval then Scheduled launches once by resolved RHEL workflow ID', () => {
    runApproval({approval: 'approved'}); runApproval({state: '-2'});
    assert.equal(launches.length, 1); assert.equal(launches[0].id, '10');
    assert.deepEqual(JSON.parse(JSON.stringify(launches[0].vars)), {snow_change_sys_id: CR, snow_request_sys_id: RITM});
    assert.equal(tables.change_request[0].u_aap_workflow_job_id, '123');
    assert.ok(tables.change_request[0].work_notes.includes('/execution/jobs/workflow/123/output'));
    runApproval({work_notes: 'ordinary update'}); runApproval({state: '-1'});
    assert.equal(launches.length, 1);
});
test('Scheduled then approval dispatches the Windows workflow', () => {
    tables.change_request[0].u_aap_build_parameters = JSON.stringify({...snapshot, server_build_os: 'windows'});
    runApproval({state: '-2'}); runApproval({approval: 'approved'});
    assert.equal(launches[0].id, '20');
});
for (const change of [{approval: 'rejected'}, {state: '4'}]) {
    test('rejected/canceled requests close incomplete without launch or later replay', () => {
        runApproval(change); assert.equal(launches.length, 0); assert.equal(tables.sc_req_item[0].state, '4');
        assert.equal(tables.change_request[0].u_aap_launch_status, 'canceled');
        runApproval({approval: 'approved', state: '-2'}); assert.equal(launches.length, 0);
    });
}
for (const [result, expected] of [
    [{status: 403, body: 'denied'}, 'failed'], [{status: 500, body: 'error'}, 'unknown'],
    [{status: 408, body: 'timeout'}, 'unknown'], [{status: 201, body: '{}'}, 'unknown'],
    [new Error('connection timed out'), 'unknown'],
]) {
    test('failed or ambiguous launches remain open and cannot automatically retry', () => {
        response = result; runApproval({approval: 'approved', state: '-2'});
        assert.equal(tables.change_request[0].u_aap_launch_status, expected);
        assert.equal(tables.change_request[0].state, '-2');
        assert.equal(tables.sc_req_item[0].state, '4');
        runApproval({work_notes: 'update'}); assert.equal(launches.length, 1);
        assert.equal(runApproval({u_aap_launch_status: 'pending'})._aborted, true);
    });
}
test('unrelated changes are ignored', () => {
    tables.change_request[0].u_aap_integration = 'other';
    runApproval({approval: 'approved', state: '-2'}); assert.equal(launches.length, 0);
});
test('snapshot and integration identity cannot be changed', () => {
    assert.equal(runApproval({u_aap_build_parameters: '{}'})._aborted, true);
    assert.equal(runApproval({u_aap_integration: 'other'})._aborted, true);
});
test('network implementation rule ignores a server-build change', () => {
    context.current = record('change_request', {...tables.change_request[0], state: '-1'});
    context.previous = record('change_request', {...tables.change_request[0], state: '-2'});
    vm.runInContext(scripts.network, context);
    assert.equal(launches.length, 0);
});
test('marked network changes retain their original implementation trigger', () => {
    const old = {...tables.change_request[0], state: '-2', correlation_display: 'network-configuration', u_aap_integration: ''};
    context.current = record('change_request', {...old, state: '-1'});
    context.previous = record('change_request', old);
    vm.runInContext(scripts.network, context);
    assert.equal(launches.length, 1);
    assert.equal(launches[0].type, 'job');
});
process.stdout.write(`${tests} generated ServiceNow rule scenarios passed\n`);
