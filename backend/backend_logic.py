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
        lease_id = result["data"]["id"]
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
    """
    input data:
    {
        "title": "TITLE OF LEASE / ADDRESS",
        "user": "NAME OF USER",
        "raw_text": "RAW TEXT GIVEN (long form text)"
    }

    output data:
    {
        "title": "TITLE OF LEASE / ADDRESS / USER",
        "basic_info": {
            "address": "ADDRESS OF PROPERTY"
        },
        "overview": {
            "risk_score": "RISK SCORE BASED ON FACTORS DETERMINED (0-100, INTEGER, HIGHER SCORES=BETTER)",
            "overview_contents": "A 2-minute LONG OVERVIEW OF THE PROS AND CONS OF THE SPECIFIC LEASE, AND HOW THIS MAY AFFECT THE RENTER",
            "rent_monthly": "MONTHLY RENT FROM LEASE (decimal)",
            "down_payment": "SECURITY DEPOSIT (decimal)",
            "duration": "DURATION OF LEASE (IN DAYS, INTEGER)",
            "notice_period": "PERIOD OF WITHDRAWAL NOTICE (IN DAYS, INTEGER)"
        },
        "results": [
            {
                "risk_flag": "RISK LEVEL OF ANNOTATION (enum: either b|m|g, representing red/yellow/green or bad/mixed/good)",
                "risk_score": "RISK SCORE OF ANNOTATION (enum: either H(high), M(medium), or L(low) depending on impact)",
                "risk_title": "TITLE OF CLAUSE/POLICY WHICH CAUSES ANNOTATION",
                "risk_contents": "SHORT, <50 WORD DESCRIPTION JUSTIFYING RISK AND LISTING POTENTIAL IMPACTS",
                "risk_origin": "SPECIFIC TEXT FROM LEASE WHICH CAUSES RISK"
            }
        ],
        "annotations": [
            {"annotation_text": "EXACT TEXT FROM THE LEASE AGREEMENT",
            "annotation_level": "b(bad)|m(medium)|g(good) - RISK LEVEL OF THE ANNOTATION",
            "annotation_desc": "CONCISE DESCRIPTION OF THE ANNOTATION, JUSTIFICATION OF LEVEL+IMPACT"}
        ],
        "questions": [
            {
            "question_priority": "h(high), m(medium), l(low) - PRIORITY LEVEL OF THE QUESTION, DETERMINED BY IMPACT AND URGENCY",
            "question_title": "A QUESTION THE RENTER SHOULD ASK THE LANDLORD/LEASE OFFERER, BASED ON THE ANNOTATIONS AND OVERVIEW",
            "question_explaination": "A BRIEF EXPLANATION OF WHY THIS QUESTION IS IMPORTANT AND WHAT THE RENTER SHOULD KNOW IN ORDER TO ASK THIS QUESTION"
            }
        ]
    }
    important. DO NOT PUT ANY CONTROL CHARACTERS IN THE STRINGS (e.g., \n, \t, etc.) AND MAKE SURE TO ESCAPE ANY QUOTES PROPERLY. THIS CAN CAUSE ISSUES WITH SQL QUERIES AND JSON PARSING.
    """
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
        "overview_content": part1response["overview_contents"],
        "risk_val": part1response["risk_score"],
        "cost_mo": float(part1response["rent_monthly"]),
        "cost_dep": float(part1response["down_payment"]),
        "duration": int(part1response["duration"]),
        "period": int(part1response["notice_period"])
    }
    operation_result = sb_connector.insert_data("ai_overviews", leaseInfo)
    if operation_result["status"] == "error":
        raise Exception(f"Error inserting lease info: {operation_result['message']}")

    pull_result = sb_connector.pull_column("ai_overviews", columns="id", criteria={"lease_id": lease_id})
    if pull_result["status"] == "error":
        raise Exception(f"Error retrieving overview_id: {pull_result['message']}")
    if not pull_result.get("data"):
        raise Exception("No overview found with the given lease_id")
    overview_id = pull_result["data"][0]["id"]
    # part 2: clause results (ai_annotations)
    # will loop through each annotation and insert into ai_annotations, with foreign key to leases
    for result in response["results"]:
        result["lease_id"] = lease_id
        result["ov_id"] = overview_id
        operation_result = sb_connector.insert_data("overview_results", result)
        if operation_result["status"] == "error":
            raise Exception(f"Error inserting overview result: {operation_result['message']}")
    

    # part 3: annotations (translated will come later, for now just store as is)
    for annotation in response["annotations"]:
        annotation["lease_id"] = lease_id
        operation_result = sb_connector.insert_data("annotations", annotation)
        if operation_result["status"] == "error":
            raise Exception(f"Error inserting annotation: {operation_result['message']}")
    
    # part 4: questions
    for question in response["questions"]:
        question["lease_id"] = lease_id
        operation_result = sb_connector.insert_data("questions", question)
        if operation_result["status"] == "error":
            raise Exception(f"Error inserting question: {operation_result['message']}")
        
    # assuming everything works
    return {"status": "success", "lease_id": lease_id}

# adds translations, given a dict of annotation_id: translated_text. will update annotations table with translated text and set translated to true
def add_translations(lease_id, translations, language_code): 
    # lease_id: lease id, translations: list(tuple(content_type="o(overview)/q(question)/a(annotation)/r(result)",obj_id=int,translated_data=string("translatedpart1|translatedpart2") seperated with bar (|))), language_code: language code of translation (e.g., "es" for Spanish)
    # to do: add translation, set translated to true, add language code to annotation, insert into translations table with annotation_id, translated_content, and language_code
    object_tables = {
        "q": "questions",
        "a": "annotations",
        "o": "ai_overviews",
        "r": "overview_results"
    }
    for translation in translations:
        content_type, obj_id, translated_data = translation
        table_name = object_tables.get(content_type)
        first_result = sb_connector.update_data(table_name, query={"id": obj_id}, new_data={"translated": True})
        if first_result["status"] == "error":
            raise Exception(f"Error updating translation status: {first_result['message']}")
        second_result = sb_connector.insert_data("translations", {"lease_id": lease_id, "obj_type": content_type, "obj_id": obj_id, "translation_content": translated_data, "language_code": language_code})
        if second_result["status"] == "error":
            raise Exception(f"Error inserting translation: {second_result['message']}")
        
    return {"status": "success", "translations_added": len(translations)}




# pulls data from database, ready to fill into report template. returns error if lease_id is invalid or if any of the data is missing
def pull_report_data(lease_id=None,owner_id=None):
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
    
    results_result = sb_connector.pull_data("overview_results", query={"lease_id": lease_id})
    if results_result and results_result.get("status") == "success" and results_result.get("data"):
        results_data = results_result["data"]
    else:        
        return {"status": "error", "message": "No results found for the given lease_id"}
    
    annotations_result = sb_connector.pull_data("annotations", query={"lease_id": lease_id})
    if annotations_result and annotations_result.get("status") == "success" and annotations_result.get("data"):
        annotations_data = annotations_result["data"]
    else:
        return {"status": "error", "message": "No annotations found for the given lease_id"}
    
    questions_result = sb_connector.pull_data("questions", query={"lease_id": lease_id})
    if questions_result and questions_result.get("status") == "success" and questions_result.get("data"):
        questions_data = questions_result["data"]
    else:
        return {"status": "error", "message": "No questions found for the given lease_id"}

    """
    result format:
    {
        {
        "status": "success",
        "overview": {
            "ov_id": 6,
            "created_at": "2026-03-01T04:29:23.81147+00:00",
            "lease_id": 11,
            "overview_content": "This 12-month urban residential lease provides a generally balanced risk profile with several tenant-friendly protections, though it includes a few moderate financial considerations. The monthly rent is aligned with comparable downtown units, and the security deposit is limited to one month’s rent, keeping upfront costs manageable. The fixed-term structure ensures rental price stability for the duration of the agreement, protecting the tenant from mid-term increases. Utilities such as water and internet are included, reducing variable monthly expenses and simplifying budgeting. The lease also contains a clearly defined maintenance response timeframe, which enhances accountability and tenant protection. However, the agreement includes a mandatory professional cleaning fee deducted from the security deposit upon move-out, which may reduce refund amounts regardless of property condition. There is also a subletting restriction requiring landlord approval, potentially limiting flexibility. While late fees are capped, they apply immediately after a short grace period. Overall, the lease offers good cost predictability and reasonable protections, but tenants should be comfortable with moderate flexibility limitations and defined move-out costs.",
            "risk_val": 71,
            "cost_mo": 2100,
            "cost_dep": 2100,
            "duration": 365,
            "period": 60
        },
        "results": [
            {
            "id": 9,
            "ov_id": 6,
            "risk_flag": "g",
            "risk_score": "L",
            "risk_title": "Included Utilities",
            "risk_contents": "Water and internet included in rent. Reduces monthly variability and improves budgeting predictability.",
            "risk_origin": "Landlord shall provide water service and standard internet access at no additional charge to Tenant."
            },
            {
            "id": 10,
            "lease_id": 11,
            "ov_id": 6,
            "risk_flag": "b",
            "risk_score": "M",
            "risk_title": "Mandatory Cleaning Fee",
            "lease_id": 11,
            "risk_contents": "Non-negotiable professional cleaning fee deducted from deposit, reducing potential refund regardless of unit condition.",
            "risk_origin": "A mandatory $250 professional cleaning fee shall be deducted from the security deposit upon Tenant’s move-out."
            },
            {
            "id": 11,
            "lease_id": 11,
            "ov_id": 6,
            "risk_flag": "m",
            "risk_score": "M",
            "risk_title": "Subletting Restrictions",
            "risk_contents": "Requires written landlord approval for subleasing. Limits tenant flexibility in relocation scenarios.",
            "risk_origin": "Tenant may not sublease the Premises without prior written consent from Landlord."
            },
            {
            "id": 12,
            "lease_id": 11,
            "ov_id": 6,
            "risk_flag": "m",
            "risk_score": "L",
            "risk_title": "Late Fee After Short Grace Period",
            "risk_contents": "Late fee applied after 3-day grace period. Moderate financial impact if payment timing issues arise.",
            "risk_origin": "If rent is not received within three (3) days of the due date, a late fee of 4% of monthly rent shall apply."
            }
        ],
        "annotations": [
            {
            "annotation_id": 9,
            "lease_id": 11,
            "annotation_level": "g",
            "annotation_desc": "Included utilities reduce monthly cost uncertainty and enhance overall lease value.",
            "translated": false,
            "translation_id": null,
            "annotation_text": "Landlord shall provide water service and standard internet access at no additional charge to Tenant."
            },
            {
            "annotation_id": 10,
            "lease_id": 11,
            "annotation_level": "b",
            "annotation_desc": "Automatic deduction reduces deposit refund regardless of property condition.",
            "translated": false,
            "translation_id": null,
            "annotation_text": "A mandatory $250 professional cleaning fee shall be deducted from the security deposit upon Tenant’s move-out."
            },
            {
            "annotation_id": 11,
            "lease_id": 11,
            "annotation_level": "m",
            "annotation_desc": "Limits flexibility; approval requirement may complicate relocation or temporary absence.",
            "translated": false,
            "translation_id": null,
            "annotation_text": "Tenant may not sublease the Premises without prior written consent from Landlord."
            },
            {
            "annotation_id": 12,
            "lease_id": 11,
            "annotation_level": "m",
            "annotation_desc": "Short grace period increases risk of incurring penalties from minor delays.",
            "translated": false,
            "translation_id": null,
            "annotation_text": "If rent is not received within three (3) days of the due date, a late fee of 4% of monthly rent shall apply."
            }
        ]
    }
    """
    return { # if success
        "status": "success",
        "results": results_data,
        "overview": overview_data,
        "annotations": annotations_data,
        "questions": questions_data
    }

# gets translated content given lease_id and language code. returns error if lease_id is invalid or if no translations found
def get_translated_report_data(lease_id, language_code):
    # returns translated content for overview, results, and annotations based on lease_id and language_code. if no translations found for a specific field, will return original content for that field
    # Get base report data
    report_data = pull_report_data(lease_id=lease_id)
    if report_data.get("status") == "error":
        return report_data
    
    # Fetch all translations for this lease and language
    translations_result = sb_connector.pull_data("translations", query={"lease_id": lease_id, "language_code": language_code})
    if translations_result.get("status") == "error":
        return {"status": "error", "message": f"Error fetching translations: {translations_result['message']}"}
    
    if not translations_result.get("data"):
        return {"status": "error", "message": f"No translations found for language: {language_code}"}
    
    # Create a map of obj_type + obj_id -> translated_content for quick lookup
    translation_map = {}
    for trans in translations_result["data"]:
        key = (trans["obj_type"], trans["obj_id"])
        translation_map[key] = trans["translation_content"]
    
    # Define which fields correspond to each object type (in pipe order)
    object_fields = {
        "o": ["overview_content"],
        "r": ["risk_title", "risk_contents"],
        "q": ["question_title", "question_explaination"],
        "a": ["annotation_text", "annotation_desc"]
    }
    
    # Replace overview fields
    if report_data.get("overview"):
        overview = report_data["overview"]
        overview_id = overview.get("id")
        if overview_id and ("o", overview_id) in translation_map:
            translated_parts = translation_map[("o", overview_id)].split("|")
            fields = object_fields.get("o", [])
            for idx, field in enumerate(fields):
                if idx < len(translated_parts):
                    overview[field] = translated_parts[idx]
    
    # Replace results fields
    if report_data.get("results"):
        for result in report_data["results"]:
            result_id = result.get("id")
            if result_id and ("r", result_id) in translation_map:
                translated_parts = translation_map[("r", result_id)].split("|")
                fields = object_fields.get("r", [])
                for idx, field in enumerate(fields):
                    if idx < len(translated_parts):
                        result[field] = translated_parts[idx]
    
    # Replace annotations fields
    if report_data.get("annotations"):
        for annotation in report_data["annotations"]:
            annotation_id = annotation.get("annotation_id")
            if annotation_id and ("a", annotation_id) in translation_map:
                translated_parts = translation_map[("a", annotation_id)].split("|")
                fields = object_fields.get("a", [])
                for idx, field in enumerate(fields):
                    if idx < len(translated_parts):
                        annotation[field] = translated_parts[idx]
    
    # Replace questions fields
    if report_data.get("questions"):
        for question in report_data["questions"]:
            question_id = question.get("id")
            if question_id and ("q", question_id) in translation_map:
                translated_parts = translation_map[("q", question_id)].split("|")
                fields = object_fields.get("q", [])
                for idx, field in enumerate(fields):
                    if idx < len(translated_parts):
                        question[field] = translated_parts[idx]
    
    return report_data
