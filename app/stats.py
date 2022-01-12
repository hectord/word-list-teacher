
from collections import defaultdict
from store import DbWordAttempt, load_database, DbSession, DbUser

USER = 'user'


if __name__ == '__main__':
    load_database('learn.db')

    attempts_by_word = defaultdict(list)

    for a in (DbWordAttempt
              .select()
              .join(DbSession)
              .join(DbUser)
              .where(DbUser.email == USER)
              .order_by(DbWordAttempt.time)):
        attempts_by_word[a.word].append(a)

    print(f'word count={len(attempts_by_word)}')

    for i in range(1, 10):
        nb_ok = 0
        nb_nok = 0

        for word, attempts in attempts_by_word.items():
            success = [attempt.success for attempt in attempts]

            for j in range(i, len(attempts)):
                assert len(success[j-i:j]) == len([True] * i)

                if success[j-i:j] == [True] * i:
                    if success[j]:
                        nb_ok += 1
                    else:
                        nb_nok += 1

        if nb_ok + nb_nok != 0:
            prob_ok = nb_ok / (nb_ok + nb_nok)
            total = nb_ok + nb_nok
            print(f'prob(OK|attempts={i} OK)={prob_ok:#.2f}', f'total={total}')
