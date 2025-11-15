"""
교수 및 직원 정보 크롤러
"""
from typing import List, Tuple, Optional
from bs4 import BeautifulSoup
from .base_crawler import BaseCrawler
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import CrawlerConfig
from utils import korean_to_iso8601


class ProfessorCrawler(BaseCrawler):
    """정교수 크롤러"""

    def __init__(self):
        super().__init__(
            board_type='professor',
            base_url=CrawlerConfig.BASE_URLS['professor']
        )

    def extract_from_url(self, url: str) -> Optional[Tuple[str, str, any, any, str, str]]:
        """
        단일 URL이 아닌 페이지 전체 교수 목록을 크롤링하므로 사용 안 함
        """
        return None

    def crawl_all(self) -> List[Tuple[str, str, any, any, str, str]]:
        """
        교수 정보 전체 크롤링 (페이지 기반)

        Returns:
            [(title, text, image_list, attachment_list, date, url), ...] 리스트
        """
        all_data = []

        print(f"\n{'='*80}")
        print(f"🌐 {self.board_type.upper()} 크롤링 시작")
        print(f"{'='*80}\n")

        try:
            response = self.fetch_with_retry(self.base_url)
            if response is None:
                return all_data

            soup = BeautifulSoup(response.text, "html.parser")

            # 교수 정보가 담긴 요소들 선택
            dr_div = soup.find("div", id="dr")
            if not dr_div:
                print("⚠️  교수 정보를 찾을 수 없습니다.")
                return all_data

            professor_elements = dr_div.find_all("li")

            for professor in professor_elements:
                # 이미지 URL 추출
                image_element = professor.find("div", class_="dr_img")
                if image_element:
                    img_tag = image_element.find("img")
                    image_content = img_tag["src"] if img_tag else "Unknown Image URL"
                else:
                    image_content = "Unknown Image URL"

                # 이름 추출
                name_element = professor.find("div", class_="dr_txt")
                if name_element:
                    h3_tag = name_element.find("h3")
                    title = h3_tag.get_text(strip=True) if h3_tag else "Unknown Name"
                else:
                    title = "Unknown Name"

                # 연락처와 이메일 추출
                contact_info = professor.find("div", class_="dr_txt")
                if contact_info:
                    dd_tags = contact_info.find_all("dd")
                    contact_number = dd_tags[0].get_text(strip=True) if len(dd_tags) > 0 else "Unknown Contact Number"
                    email = dd_tags[1].get_text(strip=True) if len(dd_tags) > 1 else "Unknown Email"
                else:
                    contact_number = "Unknown Contact Number"
                    email = "Unknown Email"

                text_content = f"{title}, {contact_number}, {email}"

                # 날짜와 URL 설정 (교수 정보는 기준일로 통일)
                date = korean_to_iso8601("작성일24-01-01 00:00")

                prof_url_element = professor.find("a")
                prof_url = prof_url_element["href"] if prof_url_element else "Unknown URL"

                # 데이터 추가 (이미지를 리스트로, 첨부파일은 빈 리스트)
                image_list = [image_content] if image_content != "Unknown Image URL" else []
                all_data.append((title, text_content, image_list, [], date, prof_url))

        except Exception as e:
            print(f"❌ 교수 정보 크롤링 오류: {e}")

        print(f"\n{'='*80}")
        print(f"✅ {self.board_type.upper()} 크롤링 완료! {len(all_data)}개 수집됨")
        print(f"{'='*80}\n")

        return all_data


class GuestProfessorCrawler(BaseCrawler):
    """초빙교수 크롤러"""

    def __init__(self):
        super().__init__(
            board_type='guest_professor',
            base_url=CrawlerConfig.BASE_URLS['guest_professor']
        )

    def extract_from_url(self, url: str) -> Optional[Tuple[str, str, any, any, str, str]]:
        """사용 안 함"""
        return None

    def crawl_all(self) -> List[Tuple[str, str, any, any, str, str]]:
        """초빙교수 정보 전체 크롤링"""
        all_data = []

        print(f"\n{'='*80}")
        print(f"🌐 {self.board_type.upper()} 크롤링 시작")
        print(f"{'='*80}\n")

        try:
            response = self.fetch_with_retry(self.base_url)
            if response is None:
                return all_data

            soup = BeautifulSoup(response.text, "html.parser")

            # 교수 정보가 담긴 요소들 선택
            student_div = soup.find("div", id="Student")
            if not student_div:
                print("⚠️  초빙교수 정보를 찾을 수 없습니다.")
                return all_data

            professor_elements = student_div.find_all("li")

            for professor in professor_elements:
                # 이미지 URL 추출
                image_element = professor.find("div", class_="img")
                if image_element:
                    img_tag = image_element.find("img")
                    image_content = img_tag["src"] if img_tag else "Unknown Image URL"
                else:
                    image_content = "Unknown Image URL"

                # 이름 추출
                name_element = professor.find("div", class_="cnt")
                if name_element:
                    name_div = name_element.find("div", class_="name")
                    title = name_div.get_text(strip=True) if name_div else "Unknown Name"
                else:
                    title = "Unknown Name"

                # 연락처와 이메일 추출
                contact_place_element = professor.find("div", class_="dep")
                contact_place = contact_place_element.get_text(strip=True) if contact_place_element else "Unknown Contact Place"

                email_element = professor.find("dl", class_="email")
                if email_element:
                    dd_tag = email_element.find("dd")
                    if dd_tag:
                        a_tag = dd_tag.find("a")
                        email = a_tag.get_text(strip=True) if a_tag else "Unknown Email"
                    else:
                        email = "Unknown Email"
                else:
                    email = "Unknown Email"

                # 텍스트 내용 조합
                text_content = f"성함(이름):{title}, 연구실(장소):{contact_place}, 이메일:{email}"

                # 날짜와 URL 설정 (교수 정보는 기준일로 통일)
                date = korean_to_iso8601("작성일24-01-01 00:00")
                prof_url = self.base_url

                # 데이터 추가 (이미지를 리스트로, 첨부파일은 빈 리스트)
                image_list = [image_content] if image_content != "Unknown Image URL" else []
                all_data.append((title, text_content, image_list, [], date, prof_url))

        except Exception as e:
            print(f"❌ 초빙교수 정보 크롤링 오류: {e}")

        print(f"\n{'='*80}")
        print(f"✅ {self.board_type.upper()} 크롤링 완료! {len(all_data)}개 수집됨")
        print(f"{'='*80}\n")

        return all_data


class StaffCrawler(BaseCrawler):
    """직원 크롤러"""

    def __init__(self):
        super().__init__(
            board_type='staff',
            base_url=CrawlerConfig.BASE_URLS['staff']
        )

    def extract_from_url(self, url: str) -> Optional[Tuple[str, str, any, any, str, str]]:
        """사용 안 함"""
        return None

    def crawl_all(self) -> List[Tuple[str, str, any, any, str, str]]:
        """직원 정보 전체 크롤링"""
        all_data = []

        print(f"\n{'='*80}")
        print(f"🌐 {self.board_type.upper()} 크롤링 시작")
        print(f"{'='*80}\n")

        try:
            response = self.fetch_with_retry(self.base_url)
            if response is None:
                return all_data

            soup = BeautifulSoup(response.text, "html.parser")

            # 직원 정보가 담긴 요소들 선택
            student_div = soup.find("div", id="Student")
            if not student_div:
                print("⚠️  직원 정보를 찾을 수 없습니다.")
                return all_data

            staff_elements = student_div.find_all("li")

            for staff in staff_elements:
                # 이미지 URL 추출
                image_element = staff.find("div", class_="img")
                if image_element:
                    img_tag = image_element.find("img")
                    image_content = img_tag["src"] if img_tag else "Unknown Image URL"
                else:
                    image_content = "Unknown Image URL"

                # 이름 추출
                cnt_element = staff.find("div", class_="cnt")
                if cnt_element:
                    h1_tag = cnt_element.find("h1")
                    title = h1_tag.get_text(strip=True) if h1_tag else "Unknown Name"
                else:
                    title = "Unknown Name"

                # 연락처 추출
                contact_number_element = staff.find("span", class_="period")
                contact_number = contact_number_element.get_text(strip=True) if contact_number_element else "Unknown Contact Number"

                # 연구실 위치, 이메일, 담당 업무 추출
                contact_info = staff.find_all("dl", class_="dep")
                contact_place = contact_info[0].find("dd").get_text(strip=True) if len(contact_info) > 0 and contact_info[0].find("dd") else "Unknown Contact Place"

                email_dd = contact_info[1].find("dd") if len(contact_info) > 1 else None
                if email_dd:
                    email_a = email_dd.find("a")
                    email = email_a.get_text(strip=True) if email_a else "Unknown Email"
                else:
                    email = "Unknown Email"

                role_dd = contact_info[2].find("dd") if len(contact_info) > 2 else None
                role = role_dd.get_text(strip=True) if role_dd else "Unknown Role"

                # 텍스트 내용 조합
                text_content = f"성함(이름):{title}, 연락처(전화번호):{contact_number}, 사무실(장소):{contact_place}, 이메일:{email}, 담당업무:{role}"

                # 날짜와 URL 설정 (교수 정보는 기준일로 통일)
                date = korean_to_iso8601("작성일24-01-01 00:00")
                staff_url = self.base_url

                # 데이터 추가 (이미지를 리스트로, 첨부파일은 빈 리스트)
                image_list = [image_content] if image_content != "Unknown Image URL" else []
                all_data.append((title, text_content, image_list, [], date, staff_url))

        except Exception as e:
            print(f"❌ 직원 정보 크롤링 오류: {e}")

        print(f"\n{'='*80}")
        print(f"✅ {self.board_type.upper()} 크롤링 완료! {len(all_data)}개 수집됨")
        print(f"{'='*80}\n")

        return all_data
