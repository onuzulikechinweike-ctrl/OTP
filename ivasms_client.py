import cloudscraper
import gzip
import brotli
import re
import time
import json
from bs4 import BeautifulSoup
from loguru import logger


class IVASSMSClient:
    def __init__(self, email, password):
        self.email = email
        self.password = password
        self.scraper = cloudscraper.create_scraper()
        self.base_url = "https://www.ivasms.com"
        self.logged_in = False
        self.csrf_token = None
        self.country_ranges = {}  # {country_name: {range_id: range_number}}

        self.scraper.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                          '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,'
                      'image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        })

    def _decompress(self, response):
        encoding = response.headers.get('Content-Encoding', '').lower()
        content = response.content
        try:
            if encoding == 'gzip':
                content = gzip.decompress(content)
            elif encoding == 'br':
                content = brotli.decompress(content)
            return content.decode('utf-8', errors='replace')
        except Exception as e:
            logger.error(f"Decompress error: {e}")
            return response.text

    def login(self):
        """Login to IVASMS and get CSRF token."""
        logger.info("Logging into IVASMS...")
        try:
            # Get login page for CSRF token
            resp = self.scraper.get(f"{self.base_url}/login", timeout=15)
            html = self._decompress(resp)
            soup = BeautifulSoup(html, 'html.parser')

            # Extract CSRF token
            token_input = soup.find('input', {'name': '_token'})
            if token_input:
                self.csrf_token = token_input['value']
            else:
                # Try meta tag
                meta = soup.find('meta', {'name': 'csrf-token'})
                if meta:
                    self.csrf_token = meta['content']

            if not self.csrf_token:
                logger.error("Could not find CSRF token on login page")
                return False

            logger.info(f"Got CSRF token: {self.csrf_token[:20]}...")

            # POST login
            login_data = {
                '_token': self.csrf_token,
                'email': self.email,
                'password': self.password,
            }

            resp = self.scraper.post(
                f"{self.base_url}/login",
                data=login_data,
                headers={
                    'Origin': self.base_url,
                    'Referer': f"{self.base_url}/login",
                },
                timeout=15
            )

            html = self._decompress(resp)

            # Check if login succeeded
            if 'dashboard' in resp.url.lower() or 'portal' in resp.url.lower():
                self.logged_in = True
                logger.info("Successfully logged into IVASMS!")
                # Refresh CSRF token from dashboard
                soup = BeautifulSoup(html, 'html.parser')
                token_input = soup.find('input', {'name': '_token'})
                if token_input:
                    self.csrf_token = token_input['value']
                return True
            elif 'Invalid' in html or 'incorrect' in html.lower():
                logger.error("Login failed: Invalid credentials")
                return False
            else:
                logger.warning(f"Login redirected to: {resp.url}")
                # Try to extract CSRF from redirected page
                soup = BeautifulSoup(html, 'html.parser')
                token_input = soup.find('input', {'name': '_token'})
                if token_input:
                    self.csrf_token = token_input['value']
                    self.logged_in = True
                    return True
                return False

        except Exception as e:
            logger.error(f"Login exception: {e}")
            return False

    def _ensure_login(self):
        """Ensure we're logged in, re-login if needed."""
        if not self.logged_in:
            return self.login()
        return True

    def get_my_numbers(self):
        """
        Fetch all numbers from Client System > My Numbers.
        Returns: {country_name: [list of phone numbers with + prefix]}
        """
        if not self._ensure_login():
            return {}

        logger.info("Fetching my numbers from IVASMS...")
        countries = {}

        try:
            # Access the my numbers page
            resp = self.scraper.get(
                f"{self.base_url}/portal/mynumbers",
                headers={'Referer': f"{self.base_url}/portal/dashboard"},
                timeout=15
            )
            html = self._decompress(resp)

            # Update CSRF token
            soup = BeautifulSoup(html, 'html.parser')
            token_input = soup.find('input', {'name': '_token'})
            if token_input:
                self.csrf_token = token_input['value']

            # Parse the table — look for country sections and numbers
            # My Numbers page typically has a table with country names and numbers

            # Try to parse the numbers table
            tables = soup.find_all('table')
            for table in tables:
                rows = table.find_all('tr')
                current_country = None
                for row in rows:
                    # Check for country header
                    th = row.find('th')
                    if th:
                        country_text = th.get_text(strip=True)
                        if country_text and not country_text.startswith('#'):
                            current_country = country_text
                            if current_country not in countries:
                                countries[current_country] = []
                        continue

                    # Get phone numbers from cells
                    cells = row.find_all('td')
                    for cell in cells:
                        text = cell.get_text(strip=True)
                        # Match phone numbers (digits with possible +)
                        phone_match = re.findall(r'\+?\d{7,15}', text)
                        for phone in phone_match:
                            if current_country:
                                if not phone.startswith('+'):
                                    phone = '+' + phone
                                countries[current_country].append(phone)

            # If table parsing failed, try alternative parsing
            if not countries:
                # Look for number elements in the page
                country_sections = soup.find_all('div', class_=re.compile(r'country|range', re.I))
                for section in country_sections:
                    country_name = None
                    h_tag = section.find(['h3', 'h4', 'h5', 'strong'])
                    if h_tag:
                        country_name = h_tag.get_text(strip=True)

                    number_spans = section.find_all('span', class_=re.compile(r'number|phone', re.I))
                    for span in number_spans:
                        num_text = span.get_text(strip=True)
                        phone_match = re.findall(r'\+?\d{7,15}', num_text)
                        for phone in phone_match:
                            if not phone.startswith('+'):
                                phone = '+' + phone
                            cname = country_name or 'Unknown'
                            if cname not in countries:
                                countries[cname] = []
                            countries[cname].append(phone)

            logger.info(f"Found countries: {list(countries.keys())}")
            for c, nums in countries.items():
                logger.info(f"  {c}: {len(nums)} numbers")

            return countries

        except Exception as e:
            logger.error(f"Error fetching my numbers: {e}")
            return {}

    def get_client_active_sms(self):
        """
        Fetch Client Active SMS page to see active ranges/countries.
        Returns: {country_name: range_number}
        """
        if not self._ensure_login():
            return {}

        logger.info("Fetching client active SMS ranges...")
        country_ranges = {}

        try:
            resp = self.scraper.get(
                f"{self.base_url}/portal/client-active-sms",
                headers={'Referer': f"{self.base_url}/portal/dashboard"},
                timeout=15
            )
            html = self._decompress(resp)
            soup = BeautifulSoup(html, 'html.parser')

            # Update CSRF
            token_input = soup.find('input', {'name': '_token'})
            if token_input:
                self.csrf_token = token_input['value']

            # Look for country range sections
            # Typically the page shows country names with associated range IDs
            range_elements = soup.find_all(['div', 'tr'], class_=re.compile(r'range|country|item', re.I))
            if not range_elements:
                # Try parsing from select/option dropdowns
                selects = soup.find_all('select')
                for select in selects:
                    if 'country' in str(select.get('class', [])).lower() or 'range' in str(select.get('id', '')).lower():
                        for option in select.find_all('option'):
                            country_name = option.get_text(strip=True)
                            range_val = option.get('value', '')
                            if country_name and range_val:
                                country_ranges[country_name] = range_val

            # Parse tables
            tables = soup.find_all('table')
            for table in tables:
                rows = table.find_all('tr')
                for row in rows:
                    cells = row.find_all('td')
                    if len(cells) >= 2:
                        country_cell = cells[0].get_text(strip=True)
                        range_cell = cells[1].get_text(strip=True)
                        if country_cell and range_cell:
                            # Extract numeric range
                            range_num = re.search(r'\d+', range_cell)
                            if range_num:
                                country_ranges[country_cell] = range_num.group()

            self.country_ranges = country_ranges
            logger.info(f"Found active ranges: {country_ranges}")
            return country_ranges

        except Exception as e:
            logger.error(f"Error fetching client active SMS: {e}")
            return {}

    def get_otp_for_number(self, phone_number, phone_range, from_date="", to_date=""):
        """
        Fetch OTP message for a specific number.
        """
        if not self._ensure_login():
            return None

        logger.info(f"Fetching OTP for {phone_number} in range {phone_range}")

        # Remove + for the API call
        clean_number = phone_number.lstrip('+')

        try:
            payload = {
                '_token': self.csrf_token,
                'start': from_date,
                'end': to_date,
                'Number': clean_number,
                'Range': phone_range
            }

            headers = {
                'Accept': 'text/html, */*; q=0.01',
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'X-Requested-With': 'XMLHttpRequest',
                'Origin': self.base_url,
                'Referer': f"{self.base_url}/portal/sms/received",
            }

            resp = self.scraper.post(
                f"{self.base_url}/portal/sms/received/getsms/number/sms",
                data=payload,
                headers=headers,
                timeout=15
            )

            if resp.status_code == 200:
                html_content = self._decompress(resp)
                soup = BeautifulSoup(html_content, 'html.parser')

                # Look for OTP message in the response
                message_elem = soup.select_one(".col-9.col-sm-6 p")
                if message_elem:
                    message = message_elem.get_text(strip=True)
                    logger.info(f"OTP for {phone_number}: {message}")
                    return message

                # Try alternative selectors
                message_elem = soup.find('p', class_=re.compile(r'message|otp|code', re.I))
                if message_elem:
                    message = message_elem.get_text(strip=True)
                    return message

                # Try getting any text content as fallback
                all_text = soup.get_text(strip=True)
                if all_text and len(all_text) > 3:
                    return all_text

            logger.warning(f"No OTP found for {phone_number}")
            return None

        except Exception as e:
            logger.error(f"Error fetching OTP for {phone_number}: {e}")
            return None

    def get_sms_details_for_range(self, phone_range, from_date="", to_date=""):
        """
        Get SMS details (numbers with messages) for a specific range.
        """
        if not self._ensure_login():
            return []

        logger.info(f"Getting SMS details for range {phone_range}")

        try:
            payload = {
                '_token': self.csrf_token,
                'start': from_date,
                'end': to_date,
                'range': phone_range
            }

            headers = {
                'Accept': 'text/html, */*; q=0.01',
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'X-Requested-With': 'XMLHttpRequest',
                'Origin': self.base_url,
                'Referer': f"{self.base_url}/portal/sms/received",
            }

            resp = self.scraper.post(
                f"{self.base_url}/portal/sms/received/getsms/range/sms",
                data=payload,
                headers=headers,
                timeout=15
            )

            if resp.status_code == 200:
                html_content = self._decompress(resp)
                soup = BeautifulSoup(html_content, 'html.parser')

                numbers = []
                items = soup.find_all('div', class_=re.compile(r'row|item|number', re.I))
                for item in items:
                    phone_elem = item.select_one(".col-3:nth-child(1) p")
                    if phone_elem:
                        phone_text = phone_elem.get_text(strip=True)
                        phone_match = re.search(r'\+?\d{7,15}', phone_text)
                        if phone_match:
                            phone = phone_match.group()
                            if not phone.startswith('+'):
                                phone = '+' + phone

                            # Get the onclick attribute for ID
                            onclick_div = item.select_one(".col-sm-4")
                            id_number = ""
                            if onclick_div and onclick_div.get('onclick'):
                                id_match = re.search(r"'(\d+)'", onclick_div['onclick'])
                                if id_match:
                                    id_number = id_match.group(1)

                            numbers.append({
                                'phone': phone,
                                'id': id_number
                            })

                return numbers

            return []

        except Exception as e:
            logger.error(f"Error getting SMS details for range {phone_range}: {e}")
            return []

    def get_otp_by_range_and_number(self, phone_number, phone_range):
        """
        Convenience method to get OTP for a number in a specific range.
        Polls for up to 120 seconds.
        """
        for attempt in range(24):  # 24 * 5s = 120s
            otp = self.get_otp_for_number(phone_number, phone_range)
            if otp and otp.strip():
                # Extract just the code/number from message
                code_match = re.search(r'\b(\d{4,8})\b', otp)
                if code_match:
                    return {
                        'full_message': otp,
                        'code': code_match.group(1)
                    }
                return {
                    'full_message': otp,
                    'code': otp
                }
            logger.info(f"Attempt {attempt + 1}/24 - No OTP yet for {phone_number}, waiting...")
            time.sleep(5)

        return None