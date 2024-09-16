import React, { useEffect, useState } from 'react';
import { RealTimeFeed, KeyMetrics, QuickActions } from '@/components/Dashboard';
import { getLatestTweets } from '@/services/twitterService';
import { useAppSelector, useAppDispatch } from '@/store';
import { fetchTweets } from '@/store/tweetSlice';

// HUMAN ASSISTANCE NEEDED
// The following component may need additional refinement for production readiness.
// Please review and adjust as necessary.

const Dashboard: React.FC = () => {
  const [loading, setLoading] = useState<boolean>(true);
  const dispatch = useAppDispatch();
  const tweets = useAppSelector((state) => state.tweets.tweets);

  useEffect(() => {
    const loadTweets = async () => {
      setLoading(true);
      await dispatch(fetchTweets());
      setLoading(false);
    };

    loadTweets();
  }, [dispatch]);

  return (
    <div className="dashboard-container">
      <h1>Dashboard</h1>
      <div className="dashboard-content">
        <div className="left-column">
          <RealTimeFeed tweets={tweets} loading={loading} />
        </div>
        <div className="right-column">
          <KeyMetrics />
          <QuickActions />
        </div>
      </div>
    </div>
  );
};

export default Dashboard;