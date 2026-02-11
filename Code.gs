/**
 * Google Apps Script backend untuk PBS Telegram Bot.
 *
 * Cara pakai singkat:
 * 1) Buat Apps Script project baru.
 * 2) Copy seluruh isi file ini ke Code.gs.
 * 3) Set Script Property `SPREADSHEET_ID` ke ID Google Sheet tujuan.
 * 4) Deploy sebagai Web App (akses: Anyone).
 */

const RECORD_HEADERS = [
  'timestamp',
  'submitter_user_id',
  'submitter_username',
  'segment',
  'jenis_order',
  'bobot',
  'service_number',
  'wo_number',
  'ticket_id',
  'tanggal_open',
  'tanggal_close',
  'teknisi_1',
  'teknisi_2',
  'workzone',
  'keterangan',
];

const RECORD_SHEET_NAME = 'Records';
const USER_MAPPING_SHEET_NAME = 'UserMapping';

function doGet() {
  return jsonOutput({ ok: true, message: 'PBS Telegram Bot Apps Script is running.' });
}

function doPost(e) {
  try {
    if (!e || !e.postData || !e.postData.contents) {
      return jsonOutput({ ok: false, error: 'Missing JSON body' });
    }

    const payload = JSON.parse(e.postData.contents);
    const action = payload.action;
    const data = payload.data || {};

    switch (action) {
      case 'append_record':
        appendRecord_(data);
        return jsonOutput({ ok: true });

      case 'set_user_mapping':
        setUserMapping_(data);
        return jsonOutput({ ok: true });

      case 'get_user_mapping': {
        const result = getUserMapping_(String(data.user_id || ''));
        return jsonOutput({ ok: true, data: result });
      }

      case 'get_all_records': {
        const records = getAllRecords_();
        return jsonOutput({ ok: true, data: records });
      }

      default:
        return jsonOutput({ ok: false, error: `Unknown action: ${action}` });
    }
  } catch (err) {
    return jsonOutput({ ok: false, error: String(err) });
  }
}

function appendRecord_(record) {
  validateRequired_(record, [
    'segment',
    'jenis_order',
    'bobot',
    'service_number',
    'wo_number',
    'ticket_id',
    'tanggal_open',
    'tanggal_close',
    'teknisi_1',
    'workzone',
  ]);

  const sheet = ensureSheet_(RECORD_SHEET_NAME, RECORD_HEADERS);
  const row = RECORD_HEADERS.map((key) => normalizeCell_(record[key]));
  sheet.appendRow(row);
}

function setUserMapping_(mapping) {
  const userId = String(mapping.user_id || '').trim();
  const teknisiName = String(mapping.teknisi_name || '').trim();
  const username = String(mapping.username || '').trim();
  const updatedAt = String(mapping.updated_at || new Date().toISOString());

  if (!userId || !teknisiName) {
    throw new Error('user_id and teknisi_name are required');
  }

  const sheet = ensureSheet_(USER_MAPPING_SHEET_NAME, [
    'user_id',
    'username',
    'teknisi_name',
    'updated_at',
  ]);

  const values = sheet.getDataRange().getValues();

  // Mulai dari index 1 karena baris 1 adalah header
  for (let r = 1; r < values.length; r += 1) {
    if (String(values[r][0]) === userId) {
      sheet.getRange(r + 1, 1, 1, 4).setValues([[userId, username, teknisiName, updatedAt]]);
      return;
    }
  }

  sheet.appendRow([userId, username, teknisiName, updatedAt]);
}

function getUserMapping_(userId) {
  if (!userId) {
    return null;
  }

  const sheet = ensureSheet_(USER_MAPPING_SHEET_NAME, [
    'user_id',
    'username',
    'teknisi_name',
    'updated_at',
  ]);

  const values = sheet.getDataRange().getValues();
  for (let r = 1; r < values.length; r += 1) {
    if (String(values[r][0]) === userId) {
      return {
        user_id: String(values[r][0] || ''),
        username: String(values[r][1] || ''),
        teknisi_name: String(values[r][2] || ''),
        updated_at: String(values[r][3] || ''),
      };
    }
  }

  return null;
}

function getAllRecords_() {
  const sheet = ensureSheet_(RECORD_SHEET_NAME, RECORD_HEADERS);
  const values = sheet.getDataRange().getValues();

  if (values.length <= 1) {
    return [];
  }

  const headers = values[0].map(String);
  const rows = values.slice(1);

  return rows.map((row) => {
    const item = {};
    headers.forEach((header, i) => {
      item[header] = row[i];
    });
    return item;
  });
}

function ensureSheet_(sheetName, headers) {
  const spreadsheet = getSpreadsheet_();
  let sheet = spreadsheet.getSheetByName(sheetName);

  if (!sheet) {
    sheet = spreadsheet.insertSheet(sheetName);
  }

  if (sheet.getLastRow() === 0) {
    sheet.appendRow(headers);
  } else {
    const currentHeaders = sheet
      .getRange(1, 1, 1, headers.length)
      .getValues()[0]
      .map(String);

    const headerMismatch = headers.some((header, i) => currentHeaders[i] !== header);
    if (headerMismatch) {
      throw new Error(
        `Header mismatch on sheet "${sheetName}". Expected: ${headers.join(', ')}`
      );
    }
  }

  return sheet;
}

function getSpreadsheet_() {
  const spreadsheetId = PropertiesService.getScriptProperties().getProperty('SPREADSHEET_ID');
  if (!spreadsheetId) {
    throw new Error('Script property SPREADSHEET_ID belum di-set');
  }

  return SpreadsheetApp.openById(spreadsheetId);
}

function validateRequired_(obj, keys) {
  keys.forEach((key) => {
    const value = obj[key];
    if (value === undefined || value === null || String(value).trim() === '') {
      throw new Error(`Missing required field: ${key}`);
    }
  });
}

function normalizeCell_(value) {
  if (value === undefined || value === null) {
    return '';
  }
  return value;
}

function jsonOutput(data) {
  return ContentService
    .createTextOutput(JSON.stringify(data))
    .setMimeType(ContentService.MimeType.JSON);
}
