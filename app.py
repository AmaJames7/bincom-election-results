import mysql.connector
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import html
import os

def get_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password=os.getenv("DB_PASSWORD", ""), 
        database="bincom_test"
    )

PARTIES = ["ACN","ANPP","CDC","CPP","DPP","JP","LABO","PDP","PPA"]

def get_polling_units():
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("""
        SELECT uniqueid, polling_unit_name
        FROM polling_unit
        WHERE polling_unit_name IS NOT NULL
          AND TRIM(polling_unit_name) <> ''
        ORDER BY polling_unit_name
    """)

    units = cursor.fetchall()
    cursor.close()
    connection.close()
    return units

def get_lgas():
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("""
        SELECT lga_id, lga_name
        FROM lga
        ORDER BY lga_name
    """)

    lgas = cursor.fetchall()
    cursor.close()
    connection.close()
    return lgas

def get_wards():
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("""
        SELECT ward_id, ward_name, lga_id
        FROM ward
        ORDER BY ward_name
    """)

    wards = cursor.fetchall()
    cursor.close()
    connection.close()
    return wards


# QUESTION 1
def get_polling_unit_results(polling_unit_id):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("""
        SELECT party_abbreviation, party_score
        FROM announced_pu_results
        WHERE polling_unit_uniqueid = %s
    """, (polling_unit_id,))

    results = cursor.fetchall()
    cursor.close()
    connection.close()
    return results


# QUESTION 2
def get_lga_results(lga_id):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            apr.party_abbreviation,
            SUM(apr.party_score) AS total_score
        FROM announced_pu_results apr
        JOIN polling_unit pu
            ON apr.polling_unit_uniqueid = pu.uniqueid
        WHERE pu.lga_id = %s
        GROUP BY apr.party_abbreviation
        ORDER BY apr.party_abbreviation
    """, (lga_id,))

    results = cursor.fetchall()
    cursor.close()
    connection.close()
    return results


# QUESTION 3
def add_new_polling_unit(data):

    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            SELECT ward_id
            FROM ward
            WHERE ward_id = %s AND lga_id = %s
        """, (data["ward_id"], data["lga_id"]))

        if not cursor.fetchone():
            raise ValueError("The selected ward does not belong to the selected LGA.")

        cursor.execute("""
            INSERT INTO polling_unit
            (polling_unit_id, ward_id, lga_id, polling_unit_name)
            VALUES (%s, %s, %s, %s)
        """, (
            data["polling_unit_id"],
            data["ward_id"],
            data["lga_id"],
            data["polling_unit_name"]
        ))

        new_unit_id = cursor.lastrowid

        for party in PARTIES:

            score = int(data["score_" + party])

            if score < 0:
                raise ValueError("Party scores cannot be negative.")

            cursor.execute("""
                INSERT INTO announced_pu_results
                (
                    polling_unit_uniqueid,
                    party_abbreviation,
                    party_score,
                    entered_by_user,
                    date_entered,
                    user_ip_address
                )
                VALUES (%s, %s, %s, %s, NOW(), %s)
            """, (
                new_unit_id,
                party,
                score,
                "admin",
                "127.0.0.1"
            ))

        connection.commit()
        return new_unit_id

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()


class ElectionApp(BaseHTTPRequestHandler):

    def do_GET(self):

        parsed_url = urlparse(self.path)
        params = parse_qs(parsed_url.query)

        try:
            units = get_polling_units()
            lgas = get_lgas()
            wards = get_wards()

            unit_options = ""

            for unit in units:
                unit_options += (
                    f'<option value="{html.escape(str(unit["uniqueid"]))}">'
                    f'{html.escape(str(unit["polling_unit_name"]))}</option>'
                )

            lga_options = ""

            for lga in lgas:
                lga_options += (
                    f'<option value="{html.escape(str(lga["lga_id"]))}">'
                    f'{html.escape(str(lga["lga_name"]))}</option>'
                )

            ward_options = ""

            for ward in wards:
                ward_options += (
                    f'<option value="{html.escape(str(ward["ward_id"]))}" '
                    f'data-lga="{html.escape(str(ward["lga_id"]))}">'
                    f'{html.escape(str(ward["ward_name"]))}</option>'
                )

            # Party score fields
            party_fields = ""

            for party in PARTIES:
                party_fields += f"""
                    <label>{party}:</label>
                    <input type="number" name="score_{party}"
                           min="0" value="0" required>
                    <br><br>
                """

            page = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Bincom Election Results</title>
                <meta name="viewport" content="width=device-width, initial-scale=1">

                <style>
                    body {{
                        font-family: Arial, sans-serif;
                        margin: 30px;
                        background: #f5f5f5;
                    }}

                    section {{
                        background: white;
                        padding: 20px;
                        margin-bottom: 25px;
                        border-radius: 8px;
                    }}

                    input, select {{
                        padding: 10px;
                        margin-top: 6px;
                        margin-bottom: 12px;
                        width: 100%;
                        max-width: 400px;
                        box-sizing: border-box;
                    }}

                    button {{
                        padding: 11px 18px;
                        background: #14532d;
                        color: white;
                        border: none;
                        border-radius: 5px;
                        cursor: pointer;
                    }}

                    table {{
                        border-collapse: collapse;
                        background: white;
                        margin-top: 15px;
                    }}

                    th, td {{
                        border: 1px solid #ccc;
                        padding: 10px;
                    }}
                </style>
            </head>

            <body>

                <h1>Delta State Election Results</h1>

                <section>
                    <h2>Individual Polling Unit Results</h2>

                    <form action="/results" method="GET">
                        <label>Select Polling Unit:</label>
                        <select name="polling_unit_id" required>
                            <option value="">Choose a polling unit</option>
                            {unit_options}
                        </select>
                        <br>
                        <button type="submit">View Results</button>
                    </form>
                </section>

                <section>
                    <h2>Total Results by LGA</h2>

                    <form action="/lga-results" method="GET">
                        <label>Select LGA:</label>
                        <select name="lga_id" required>
                            <option value="">Choose an LGA</option>
                            {lga_options}
                        </select>
                        <br>
                        <button type="submit">View LGA Results</button>
                    </form>
                </section>

                <section>
                    <h2>Add New Polling Unit Results</h2>

                    <form action="/add-polling-unit" method="POST">

                        <label>Polling Unit ID:</label>
                        <input type="text" name="polling_unit_id" required>

                        <label>Polling Unit Name:</label>
                        <input type="text" name="polling_unit_name" required>

                        <label>Select LGA:</label>
                        <select name="lga_id" id="lga" required>
                            <option value="">Choose an LGA</option>
                            {lga_options}
                        </select>

                        <label>Select Ward:</label>
                        <select name="ward_id" id="ward" required>
                            <option value="">Choose a ward</option>
                            {ward_options}
                        </select>

                        <h3>Party Scores</h3>
                        {party_fields}

                        <button type="submit">Save Polling Unit Results</button>
                    </form>
                </section>

                <script>
                    const lgaSelect = document.getElementById("lga");
                    const wardSelect = document.getElementById("ward");

                    const allWards = Array.from(wardSelect.options);

                    lgaSelect.addEventListener("change", function() {{
                        const selectedLga = this.value;

                        wardSelect.innerHTML =
                            '<option value="">Choose a ward</option>';

                        allWards.forEach(function(option) {{
                            if (option.dataset.lga === selectedLga) {{
                                wardSelect.appendChild(option.cloneNode(true));
                            }}
                        }});
                    }});
                </script>

            """

            if parsed_url.path == "/results":

                unit_id = params.get("polling_unit_id", [""])[0]

                if unit_id.isdigit():
                    results = get_polling_unit_results(int(unit_id))

                    page += "<section><h2>Polling Unit Results</h2>"

                    if results:
                        page += """
                        <table>
                            <tr><th>Party</th><th>Votes</th></tr>
                        """

                        for result in results:
                            page += (
                                f'<tr><td>{html.escape(str(result["party_abbreviation"]))}</td>'
                                f'<td>{html.escape(str(result["party_score"]))}</td></tr>'
                            )

                        page += "</table>"
                    else:
                        page += "<p>No results found.</p>"

                    page += "</section>"


            elif parsed_url.path == "/lga-results":

                lga_id = params.get("lga_id", [""])[0]

                if lga_id.isdigit():
                    results = get_lga_results(int(lga_id))

                    page += "<section><h2>Summed LGA Results</h2>"

                    if results:
                        page += """
                        <table>
                            <tr><th>Party</th><th>Total Votes</th></tr>
                        """

                        for result in results:
                            page += (
                                f'<tr><td>{html.escape(str(result["party_abbreviation"]))}</td>'
                                f'<td>{html.escape(str(result["total_score"]))}</td></tr>'
                            )

                        page += "</table>"
                    else:
                        page += "<p>No results found for this LGA.</p>"

                    page += "</section>"

            page += """
            </body>
            </html>
            """

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(page.encode("utf-8"))

        except Exception as error:
            self.send_error(500, str(error))

    def do_POST(self):

        if urlparse(self.path).path != "/add-polling-unit":
            self.send_error(404, "Page not found")
            return

        try:
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length).decode("utf-8")
            params = parse_qs(post_data)

            data = {
                key: values[0]
                for key, values in params.items()
            }

            required_fields = [
                "polling_unit_id",
                "polling_unit_name",
                "ward_id",
                "lga_id"
            ]

            for field in required_fields:
                if not data.get(field, "").strip():
                    raise ValueError("Please complete all polling unit details.")

            for party in PARTIES:
                score = data.get("score_" + party, "")

                if not score.isdigit():
                    raise ValueError("Enter a valid non-negative score for every party.")

            new_unit_id = add_new_polling_unit(data)

            message = f"""
            <html>
            <head><title>Saved Successfully</title></head>
            <body style="font-family: Arial; padding: 30px;">
                <h1>Results Saved Successfully!</h1>
                <p>The new polling unit and all nine party results have been recorded.</p>
                <p>Generated polling unit record ID: {new_unit_id}</p>
                <a href="/">Return to the homepage</a>
            </body>
            </html>
            """

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(message.encode("utf-8"))

        except Exception as error:

            message = f"""
            <html>
            <body style="font-family: Arial; padding: 30px;">
                <h2>Unable to save results</h2>
                <p>{html.escape(str(error))}</p>
                <a href="/">Return to the homepage</a>
            </body>
            </html>
            """

            self.send_response(400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(message.encode("utf-8"))

server = HTTPServer(("127.0.0.1", 8000), ElectionApp)

print("Election application running at http://127.0.0.1:8000")

server.serve_forever()
