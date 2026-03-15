# vincent hsiao - vchsi - 3/1/2026
# backend_logic.py: incorporates a lot of the logic for the backend, including file handling, PDF parsing, and interactions with the SBConnector.
#from pdf_handler import PDFHandler
from sb_connector import SBConnector
import random
import json

sb_connector = SBConnector()

def get_owner_id(uname):
    result = sb_connector.pull_column("users", columns="id", criteria={"username": uname})
    if result and result.get("status") == "success" and result.get("data"):
        return result["data"][0]["id"]
    return None
"""
def process_pdf(file_path, username):
    # Step 1: Extract text from PDF
    pdf_handler = PDFHandler(file_path)
    extracted_text = pdf_handler.extract_text()
    
    # Step 2: Store extracted text in Supabase
    owner_id = get_owner_id(username)  # Example user name
    data = {
        "owner_id": owner_id,
        "pathname": f"{file_path}.pdf",
        "raw_text": extracted_text,
    }
    response = sb_connector.insert_data("pdf_data", data)
    
    return response

# will tie in with amd
"""
def check_lease(lease_id):
    # returns true if lease is valid, false otherwise
    if not lease_id:
        return False
    result = sb_connector.pull_data("leases", query={"id": lease_id})
    if result and result.get("status") == "success" and result.get("data"):
        return True
    return False

def pull_lease_data(lease_id, tables=["leases"]):
    result = sb_connector.pull_data("leases", query={"id": lease_id})
    if result and result.get("status") == "success" and result.get("data"):
        return result["data"][0]
    return None

def lease_id_by_owner(owner_id):
    result = sb_connector.pull_column("leases", columns="id", criteria={"owner_id": owner_id})
    if result and result.get("status") == "success" and result.get("data"):
        return result["data"][0]["id"]
    return None

# adds new lease data to db, returns lease_id. if new_lease=False, will just add overview and annotations to existing lease_id
def query_lease(pathname, owner_email, raw_text): # owner_id is email for now, can change later
    # creates new lease, processes it, and returns response. saves file path to db
    result = sb_connector.insert_data("leases", {"owner_id": owner_email, "pathname": pathname, "raw_text": raw_text})
    if result and result.get("status") == "success":
        #print(result)
        lease_id = result["data"][0]["id"]
        # Process the lease (e.g., run through AMD, generate overview, etc.)
        # For now, we'll just return a placeholder response
        return {"status": "success", "lease_id": lease_id}
    else:
        raise AssertionError(f"Failed to insert lease data into database for pathname={pathname!r}, owner_email={owner_email!r}")

# pull pathname given lease_id
def pull_pathname(lease_id):
    result = sb_connector.pull_column("leases", columns="pathname", criteria={"id": lease_id})
    if result and result.get("status") == "success" and result.get("data"):
        return result["data"][0]["pathname"]
    return None

# pull report data given lease_id, returns overview, results, and annotations
def query_response(response, lease_id=None, new_lease=False, new_lease_data=None):
    # response returns as a json string    
    # json string -> sql_like query
    #"ad,rn,sd,lt,np,lf,et,ut"
    """
    input data:
    {
        "title": "TITLE OF LEASE / ADDRESS",
        "user": "NAME OF USER",
        "raw_text": "RAW TEXT GIVEN (long form text)"
    }

    output data:
    {{
        "title": "{filename}",
        "text_incomplete": true/false,
        "basic_info": {{
            "address": {{
            "value": string|null,
            "evidence_quote": string|null,
            "missing_reason": string|null
            }}
        }},
        "overview": {{
            "risk_score": int,
            "overview_contents": string,
            "rent_monthly": {{
            "value": number|null,
            "evidence_quote": string|null,
            "missing_reason": string|null,
            "ambiguous": true/false
            }},
            "security_deposit": {{
            "value": number|null,
            "evidence_quote": string|null,
            "missing_reason": string|null,
            "ambiguous": true/false
            }},
            "lease_term_days": {{
            "value": int|null,
            "evidence_quote": string|null,
            "missing_reason": string|null,
            "ambiguous": true/false
            }},
            "notice_period": {{
            "value": string|null,
            "evidence_quote": string|null,
            "missing_reason": string|null
            }},
            "late_fees": {{
            "value": string|null,
            "evidence_quote": string|null,
            "missing_reason": string|null
            }},
            "early_termination": {{
            "value": string|null,
            "evidence_quote": string|null,
            "missing_reason": string|null
            }},
            "utilities": {{
            "value": string|null,
            "evidence_quote": string|null,
            "missing_reason": string|null
            }}
        }},
        "results": [
            {{
            "annotationText": "EXACT TEXT FROM THE LEASE AGREEMENT",
            "annotationLevel": "good"|"mix"|"bad",
            "annotationDesc": "CONCISE DESCRIPTION OF THE ANNOTATION, JUSTIFICATION OF LEVEL+IMPACT",
            "risk_title": string,
            "severity": "HIGH"|"MEDIUM"|"LOW",
            "evidence_location_hint": string|null
            }}
        ]
        }}
    important. DO NOT PUT ANY CONTROL CHARACTERS IN THE STRINGS (e.g., \n, \t, etc.) AND MAKE SURE TO ESCAPE ANY QUOTES PROPERLY. THIS CAN CAUSE ISSUES WITH SQL QUERIES AND JSON PARSING.
    """
    #"ad,rn,sd,lt,np,lf,et,ut"
    EVIDENCE_CODES = {
        "address": "ad",
        "rent_monthly": "rn",
        "security_deposit": "sd",
        "lease_term_days": "lt",
        "notice_period": "np",
        "late_fees": "lf",
        "early_termination": "et",
        "utilities": "ut"
    }
    if(type(response) == str):
        response = json.loads(response)
    # part 1: lease information (ai_overviews)
    part1response = response["overview"]
    if(not lease_id or new_lease):
        data = {
            "owner_id": new_lease_data["owner_id"],
            "pathname": new_lease_data["pathname"],
            "raw_text": new_lease_data["raw_text"]
        }
        operation_result = sb_connector.insert_data("leases", data)
        if operation_result["status"] == "error":
            raise Exception(f"Error inserting new lease info: {operation_result['message']}")
        pull_result = sb_connector.pull_column("leases", columns="id", criteria={"pathname": new_lease_data["pathname"]})
        if pull_result["status"] == "error":
            raise Exception(f"Error retrieving lease_id: {pull_result['message']}")
        lease_id = pull_result["data"][0]["id"]

    leaseInfo = {
        "lease_id": lease_id,
        "overview_contents": part1response["overview_contents"],
        "risk_score": part1response["risk_score"],
        "rent_monthly": part1response["rent_monthly"]["value"],
        "security_deposit": part1response["security_deposit"]["value"],
        "lease_term_days": part1response["lease_term_days"]["value"],
        "notice_period": part1response["notice_period"]["value"],
        "late_fees": part1response["late_fees"]["value"],
        "utilities": part1response["utilities"]["value"]
    }
    operation_result = sb_connector.insert_data("ai_overviews", leaseInfo)
    if operation_result["status"] == "error":
        raise Exception(f"Error inserting lease info: {operation_result['message']}")

    # add evidence
    for field, code in EVIDENCE_CODES.items():
        field_info = part1response.get(field)
        if field_info and field_info.get("value") is not None:
            evidence_data = {
                "lease_id": lease_id,
                "value": field_info.get("value"),
                "evidence_quote": field_info.get("evidence_quote"),
                "missing_reason": field_info.get("missing_reason"),
                "ambiguous": field_info.get("ambiguous", False),
                "evidence_code": f"{lease_id}{code}"
            }
            operation_result = sb_connector.insert_data("evidence", evidence_data)
            if operation_result["status"] == "error":
                raise Exception(f"Error inserting evidence for {field}: {operation_result['message']}")
    
    """
    {{
            "annotationText": "EXACT TEXT FROM THE LEASE AGREEMENT",
            "annotationLevel": "good"|"mix"|"bad",
            "annotationDesc": "CONCISE DESCRIPTION OF THE ANNOTATION, JUSTIFICATION OF LEVEL+IMPACT",
            "risk_title": string,
            "severity": "HIGH"|"MEDIUM"|"LOW",
            "evidence_location_hint": string|null
            }}
    """
    

    # part 2: annotations (translated will come later, for now just store as is)
    for annotation in response["results"]:
        annotation["lease_id"] = lease_id
        operation_result = sb_connector.insert_data("annotations", annotation)
        if operation_result["status"] == "error":
            raise Exception(f"Error inserting annotation: {operation_result['message']}")
    
    # part 3: questions
    for question in response.get("questions", []):
        question["lease_id"] = lease_id
        operation_result = sb_connector.insert_data("questions", question)
        if operation_result["status"] == "error":
            raise Exception(f"Error inserting question: {operation_result['message']}")
    
    # assuming everything works
    return {"status": "success", "lease_id": lease_id}

# depreciationed, may bring back later if we want to have a separate endpoint for adding translations instead of doing it in app.py
"""
# adds translations, given a dict of annotation_id: translated_text. will update annotations table with translated text and set translated to true
def add_translations(lease_id, translations, language_code): 
    # lease_id: lease id, translations: list(tuple(content_type="o(overview)/q(question)/a(annotation)/r(result)",obj_id=int,translated_data=string("translatedpart1|translatedpart2") seperated with bar (|))), language_code: language code of translation (e.g., "es" for Spanish)
    # to do: add translation, set translated to true, add language code to annotation, insert into translations table with annotation_id, translated_content, and language_code
    object_tables = {
        "e": "evidence",
        "a": "annotations",
        "o": "ai_overviews"
    }
    lease_data = pull_lease_data(lease_id)
    if not lease_data:
        return {"status": "error", "message": "Invalid lease_id"}
    # for each translation, update the corresponding table to set translated to true, then insert a new row into the translations table with lease_id, obj_type, obj_id, translated_content, and language_code
    
        
    return {"status": "success", "translations_added": len(translations)}


"""

# pulls data from database, ready to fill into report template. returns error if lease_id is invalid or if any of the data is missing
def pull_report_data(lease_id=None,owner_id=None):
    EVIDENCE_CODES = {
        "address": "ad",
        "rent_monthly": "rn",
        "security_deposit": "sd",
        "lease_term_days": "lt",
        "notice_period": "np",
        "late_fees": "lf",
        "early_termination": "et",
        "utilities": "ut"
    }
    assert lease_id or owner_id, "Must provide either lease_id or owner_id"
    if owner_id:
        result = sb_connector.pull_data("leases", query={"owner_id": owner_id})
        if result and result.get("status") == "success" and result.get("data"):
            lease_id = result["data"][0]["id"]
        else:
            return {"status": "error", "message": "No leases found for the given owner_id"}
    else:
        if(not check_lease(lease_id)):
            return {"status": "error", "message": "Invalid lease_id"}
    
    
    overview_result = sb_connector.pull_data("ai_overviews", query={"lease_id": lease_id})
    if overview_result and overview_result.get("status") == "success" and overview_result.get("data"):
        overview_data = overview_result["data"][0]
    else:
        return {"status": "error", "message": "No overview found for the given lease_id"}
    
    evidence = sb_connector.pull_data("evidence", query={"lease_id": lease_id})
    if evidence and evidence.get("status") == "success" and evidence.get("data"):
        evidence_data = evidence["data"]
    else:
        raise Exception("No evidence found for the given lease_id")
    
    for field in ["rent_monthly", "security_deposit", "lease_term_days", "notice_period", "late_fees", "early_termination", "utilities"]:
        evidence_code = f"{lease_id}{EVIDENCE_CODES[field]}"
        field_evidence = next((e for e in evidence_data if e["evidence_code"] == evidence_code), None)
        if field_evidence:
            overview_data[field] = {
                "value": field_evidence["value"],
                "evidence_quote": field_evidence["evidence_quote"],
                "missing_reason": field_evidence["missing_reason"],
                "ambiguous": field_evidence["ambiguous"]
            }
        else:
            overview_data[field] = {
                "value": None,
                "evidence_quote": None,
                "missing_reason": "No evidence found for this field",
                "ambiguous": False
            }

    annotations_result = sb_connector.pull_data("annotations", query={"lease_id": lease_id})
    if annotations_result and annotations_result.get("status") == "success" and annotations_result.get("data"):
        annotations_data = annotations_result["data"]
    else:
        return {"status": "error", "message": "No annotations found for the given lease_id"}
    return_val = []
    for annotation in annotations_data:
        return_val.append(annotation)
    return { # if success
        "status": "success",
        "overview": overview_data,
        "results": return_val,
        "questions": sb_connector.pull_data("questions", query={"lease_id": lease_id}).get("data", [])
    }


def pull_by_userid(useremail):
    result = lease_id_by_owner(useremail)
    if result:
        return pull_report_data(lease_id=result)
    else:        
        return {"status": "error", "message": "No leases found for the given user email"}
    

def pull_all_leases_by_owner(useremail):
    result = sb_connector.pull_data("leases", query={"owner_email": useremail})
    if result and result.get("status") == "success" and result.get("data"):
        # Remove raw_text from each lease in the response for security reasons
        leases = []
        for lease in result["data"]:
            lease_copy = lease.copy()
            lease_copy.pop("raw_text", None)  # Remove raw_text if it exists
            leases.append(lease_copy)
        return {"status": "success", "leases": leases}
    else:
        return {"status": "error", "message": "No leases found for the given user email"}

