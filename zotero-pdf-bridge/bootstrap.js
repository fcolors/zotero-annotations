/* Zotero PDF Bridge -- Zotero 9 minimal plugin
 *
 * GET /pdf-bridge/ping
 * GET /pdf-bridge/:itemKey[?libraryID=1]
 *
 * PDF response is base64 text. Zotero.Server.Endpoints serializes normal
 * endpoint bodies through a UTF-8 string output stream, so arbitrary raw
 * PDF bytes cannot safely be returned here.
 */

var PDF_BRIDGE_PREFIX = "Zotero PDF Bridge: ";
var PDF_BRIDGE_PING_ROUTE = "/pdf-bridge/ping";
var PDF_BRIDGE_PDF_ROUTE = "/pdf-bridge/:key";
var PDF_BRIDGE_VERSION = "0.2.2";

function log(msg) {
  Zotero.debug(PDF_BRIDGE_PREFIX + msg);
}

function textResponse(status, text) {
  return [
    status,
    {
      "Content-Type": "text/plain; charset=UTF-8",
      "Cache-Control": "no-store"
    },
    String(text) + "\n"
  ];
}

function jsonResponse(status, obj) {
  return [
    status,
    {
      "Content-Type": "application/json; charset=UTF-8",
      "Cache-Control": "no-store"
    },
    JSON.stringify(obj) + "\n"
  ];
}

function isImportedPDF(item) {
  return !!(
    item &&
    item.isAttachment && item.isAttachment() &&
    item.isPDFAttachment && item.isPDFAttachment() &&
    item.isImportedAttachment && item.isImportedAttachment()
  );
}

async function resolvePDF(item) {
  if (!item) return null;
  if (isImportedPDF(item)) return item;
  if (!item.isRegularItem || !item.isRegularItem()) return null;

  let ids = item.getAttachments ? item.getAttachments() : [];
  if (!ids.length) return null;

  let attachments = Zotero.Items.get(ids);
  for (let attachment of attachments) {
    if (isImportedPDF(attachment)) return attachment;
  }
  return null;
}

function PingEndpoint() {}
PingEndpoint.prototype = {
  supportedMethods: ["GET"],
  init(_request) {
    return jsonResponse(200, {
      ok: true,
      plugin: "zotero-pdf-bridge",
      version: PDF_BRIDGE_VERSION,
      zotero: Zotero.version,
      transport: "base64"
    });
  }
};

function PDFEndpoint() {}
PDFEndpoint.prototype = {
  supportedMethods: ["GET"],

  async init({ pathParams, searchParams }) {
    try {
      let key = String(pathParams.key || "").trim().toUpperCase();
      if (!/^[A-Z0-9]{8}$/.test(key)) {
        return textResponse(400, "invalid Zotero item key");
      }

      let libraryID = Zotero.Libraries.userLibraryID;
      let requestedLibraryID = searchParams.get("libraryID");
      if (requestedLibraryID !== null) {
        libraryID = Number(requestedLibraryID);
        if (!Number.isInteger(libraryID) || libraryID <= 0) {
          return textResponse(400, "invalid libraryID");
        }
      }

      // Zotero 9 exposes getByLibraryAndKey() synchronously. There is no
      // Zotero.Items.getByLibraryAndKeyAsync().
      let item = Zotero.Items.getByLibraryAndKey(libraryID, key);
      if (!item) {
        return textResponse(404, "item not found");
      }

      let attachment = await resolvePDF(item);
      if (!attachment) {
        return textResponse(404, "imported PDF attachment not found");
      }

      // Deliberately reject linked files: this bridge only exposes Zotero-
      // managed stored PDFs and must not become a generic Windows file reader.
      if (!isImportedPDF(attachment)) {
        return textResponse(403, "linked attachments are not allowed");
      }

      // Use Zotero's own attachment reader/base64 implementation.
      let dataURI = await attachment.attachmentDataURI;
      if (!dataURI) {
        return textResponse(404, "PDF file is not available locally");
      }

      let comma = dataURI.indexOf(",");
      if (comma < 0 || !/^data:application\/pdf;base64,/i.test(dataURI)) {
        return textResponse(500, "unexpected attachment data URI");
      }
      let body = dataURI.slice(comma + 1);

      return [
        200,
        {
          "Content-Type": "text/plain; charset=US-ASCII",
          "Cache-Control": "no-store",
          "X-PDF-Bridge-Encoding": "base64",
          "X-PDF-Bridge-Attachment-Key": attachment.key
        },
        body
      ];
    }
    catch (e) {
      Zotero.logError(e);
      let msg = (e && (e.stack || e.message)) ? (e.stack || e.message) : String(e);
      log("PDF endpoint error: " + msg);
      return textResponse(500, "internal error: " + msg);
    }
  }
};

function install() {
  log("installed");
}

async function startup({ id, version, rootURI }, reason) {
  if (Zotero.initializationPromise) {
    await Zotero.initializationPromise;
  }

  Zotero.Server.Endpoints[PDF_BRIDGE_PING_ROUTE] = PingEndpoint;
  Zotero.Server.Endpoints[PDF_BRIDGE_PDF_ROUTE] = PDFEndpoint;
  log(`started ${version}; endpoints registered`);
}

function shutdown({ id, version, rootURI }, reason) {
  delete Zotero.Server.Endpoints[PDF_BRIDGE_PING_ROUTE];
  delete Zotero.Server.Endpoints[PDF_BRIDGE_PDF_ROUTE];
  log("stopped; endpoints removed");
}

function uninstall() {
  log("uninstalled");
}
