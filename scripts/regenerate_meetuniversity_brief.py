import asyncio
from backend.database import SessionLocal
from backend.services.brief_service import brief_service

async def main():
    db = SessionLocal()
    print("=" * 80)
    print("REGENERATING MONDAY BRIEF FOR MEETUNIVERSITY (COMPANY #1)")
    print("=" * 80)

    brief = await brief_service.generate_monday_brief(db, company_id=1)
    print("\n" + "=" * 80)
    print("FULL GENERATED MONDAY MORNING STRATEGIC BRIEF (MARKDOWN EXPORT)")
    print("=" * 80 + "\n")
    print(brief.markdown_export)
    print("\n" + "=" * 80)
    db.close()

if __name__ == "__main__":
    asyncio.run(main())
